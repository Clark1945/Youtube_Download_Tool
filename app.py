import os
import re
import time
import json
import uuid
import threading
import subprocess
from functools import wraps
from dotenv import load_dotenv
from flask import (Flask, render_template, request, jsonify,
                   send_file, Response, after_this_request,
                   session, redirect, url_for)
from pytubefix import YouTube

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']

LOGIN_USERNAME = os.environ['LOGIN_USERNAME']
LOGIN_PASSWORD = os.environ['LOGIN_PASSWORD']

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
FFMPEG_PATH = os.path.join(BASE_DIR, 'ffmpeg.exe')
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

tasks = {}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name)


# ── Auth routes ──────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == LOGIN_USERNAME and password == LOGIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        error = '帳號或密碼錯誤'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Main app ─────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/api/info')
@login_required
def get_info():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': '請輸入網址'}), 400
    try:
        yt = YouTube(url)
        streams = yt.streams.filter(adaptive=True)
        seen = set()
        qualities = []
        for s in streams:
            if s.resolution and s.resolution not in seen:
                seen.add(s.resolution)
                qualities.append(s.resolution)
        qualities.sort(key=lambda x: int(x.replace('p', '')), reverse=True)
        return jsonify({'title': yt.title, 'qualities': qualities})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/download', methods=['POST'])
@login_required
def start_download():
    data = request.json
    url = (data.get('url') or '').strip()
    dl_type = data.get('type', 'video')
    resolution = data.get('resolution', '')

    if not url:
        return jsonify({'error': '請輸入網址'}), 400

    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'pending', 'progress': 0, 'file_path': None, 'filename': None, 'error': None}
    threading.Thread(target=_run_download, args=(task_id, url, dl_type, resolution), daemon=True).start()
    return jsonify({'task_id': task_id})


def _run_download(task_id, url, dl_type, resolution):
    task = tasks[task_id]
    task['status'] = 'downloading'

    def on_progress(stream, chunk, bytes_remaining):
        size = stream.filesize
        task['progress'] = int((size - bytes_remaining) / size * 100)

    try:
        yt = YouTube(url, on_progress_callback=on_progress)

        if dl_type == 'audio':
            stream = yt.streams.get_audio_only()
            tmp = stream.download(output_path=DOWNLOADS_DIR, filename=f'{task_id}_audio')
            mp3 = os.path.splitext(tmp)[0] + '.mp3'
            os.rename(tmp, mp3)
            task.update({'file_path': mp3, 'filename': sanitize_filename(yt.title) + '.mp3'})

        elif int(resolution.replace('p', '')) < 720:
            stream = yt.streams.filter(progressive=True, resolution=resolution).first()
            out = stream.download(output_path=DOWNLOADS_DIR, filename=f'{task_id}.mp4')
            task.update({'file_path': out, 'filename': sanitize_filename(yt.title) + '.mp4'})

        else:
            video_stream = yt.streams.filter(adaptive=True, resolution=resolution).first()
            ext = video_stream.mime_type.split('/')[1]
            v_path = video_stream.download(output_path=DOWNLOADS_DIR, filename=f'{task_id}_v.{ext}')
            task['progress'] = 50
            audio_stream = yt.streams.filter(only_audio=True).first()
            a_path = audio_stream.download(output_path=DOWNLOADS_DIR, filename=f'{task_id}_a.{ext}')
            out = os.path.join(DOWNLOADS_DIR, f'{task_id}.mp4')
            subprocess.run(
                [FFMPEG_PATH, '-i', v_path, '-i', a_path,
                 '-c:v', 'copy', '-c:a', 'aac', '-y', out],
                check=True, capture_output=True
            )
            os.remove(v_path)
            os.remove(a_path)
            task.update({'file_path': out, 'filename': sanitize_filename(yt.title) + '.mp4'})

        task['progress'] = 100
        task['status'] = 'done'

    except subprocess.CalledProcessError:
        task['status'] = 'error'
        task['error'] = 'FFmpeg 合併失敗，請確認 ffmpeg.exe 存在'
    except Exception as e:
        task['status'] = 'error'
        task['error'] = str(e)


@app.route('/api/progress/<task_id>')
@login_required
def get_progress(task_id):
    def generate():
        while True:
            t = tasks.get(task_id)
            if not t:
                yield f'data: {json.dumps({"status": "not_found"})}\n\n'
                break
            payload = {'status': t['status'], 'progress': t['progress'], 'error': t['error']}
            yield f'data: {json.dumps(payload)}\n\n'
            if t['status'] in ('done', 'error'):
                break
            time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/file/<task_id>')
@login_required
def get_file(task_id):
    t = tasks.get(task_id)
    if not t or t['status'] != 'done' or not t.get('file_path'):
        return jsonify({'error': '檔案尚未準備好'}), 404

    file_path = t['file_path']
    filename = t['filename']

    @after_this_request
    def cleanup(response):
        def _delete():
            time.sleep(60)
            try:
                os.remove(file_path)
            except OSError:
                pass
            tasks.pop(task_id, None)
        threading.Thread(target=_delete, daemon=True).start()
        return response

    return send_file(file_path, as_attachment=True, download_name=filename)


if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)
