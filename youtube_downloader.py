import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
from pytubefix import YouTube
import os,re
import threading


class YouTubeDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube 下載工具")
        self.root.geometry("600x400")

        # 建立主要框架
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # URL 輸入
        ttk.Label(self.main_frame, text="YouTube 網址:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(self.main_frame, width=50)
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # 下載類型選擇
        ttk.Label(self.main_frame, text="下載類型:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.download_type = tk.StringVar(value="video")
        ttk.Radiobutton(self.main_frame, text="影片", variable=self.download_type,
                        value="video").grid(row=1, column=1, sticky=tk.W)
        ttk.Radiobutton(self.main_frame, text="音訊", variable=self.download_type,
                        value="audio").grid(row=1, column=2, sticky=tk.W)

        # 影片品質選擇（預設隱藏）
        self.quality_frame = ttk.Frame(self.main_frame)
        self.quality_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        ttk.Label(self.quality_frame, text="影片品質:").grid(row=0, column=0, sticky=tk.W)
        self.quality_combobox = ttk.Combobox(self.quality_frame, state='readonly', width=47)
        self.quality_combobox.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E))

        # 儲存位置選擇
        ttk.Label(self.main_frame, text="儲存位置:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.save_path = tk.StringVar()
        self.save_path_entry = ttk.Entry(self.main_frame, textvariable=self.save_path, width=40)
        self.save_path_entry.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(self.main_frame, text="瀏覽", command=self.browse_path).grid(row=3, column=2, sticky=tk.W, pady=5)

        # 下載按鈕
        self.download_button = ttk.Button(self.main_frame, text="下載", command=self.start_download)
        self.download_button.grid(row=4, column=0, columnspan=3, pady=10)

        # 進度條
        self.progress = ttk.Progressbar(self.main_frame, length=400, mode='determinate')
        self.progress.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        # 狀態標籤
        self.status_label = ttk.Label(self.main_frame, text="")
        self.status_label.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        # 綁定URL輸入變更事件
        self.url_entry.bind('<FocusOut>', self.on_url_change)
        self.download_type.trace('w', self.on_type_change)

    def browse_path(self):
        """選擇儲存位置"""
        directory = filedialog.askdirectory()
        if directory:
            self.save_path.set(directory)

    def on_url_change(self, event=None):
        """當URL改變時更新影片品質選項"""
        url = self.url_entry.get()
        if url:
            try:
                yt = YouTube(url)
                # print(f"All source=[{[s.mine_type for s in yt.streams.all()]}]")
                if self.download_type.get() == "video":
                    streams = yt.streams.filter(adaptive='True')
                    qualities = [f"{s.resolution} ({s.mime_type})" for s in streams]
                else:
                    streams = yt.streams.get_audio_only()
                    qualities = f"{streams.abr} ({streams.mime_type})"
                self.quality_combobox['values'] = qualities
                if qualities:
                    self.quality_combobox.set(qualities[0])
            except Exception as e:
                messagebox.showerror("錯誤", f"無法取得影片資訊: {str(e)}")

    def on_type_change(self, *args):
        """當下載類型改變時更新UI"""
        if self.download_type.get() == "video":
            self.quality_frame.grid()
            self.on_url_change()
        else:
            self.quality_frame.grid_remove()

    def update_progress(self, stream, chunk, bytes_remaining):
        """更新下載進度"""
        size = stream.filesize
        downloaded = size - bytes_remaining
        progress = (downloaded / size) * 100
        self.progress['value'] = progress
        self.status_label['text'] = f"下載進度: {progress:.1f}%"
        self.root.update_idletasks()

    def start_download(self):
        """開始下載"""
        url = self.url_entry.get()
        if not url:
            messagebox.showerror("錯誤", "請輸入YouTube網址")
            return

        if not self.save_path.get():
            messagebox.showerror("錯誤", "請選擇儲存位置")
            return

        self.download_button['state'] = 'disabled'
        threading.Thread(target=self.download, daemon=True).start()

    def sanitize_filename(self,filename):
        return re.sub(r'[\/:*?"<>|]', '_', filename)  # 避免非法字元

    def download(self):
        """執行下載程序"""
        global stream
        try:
            yt = YouTube(self.url_entry.get(), on_progress_callback=self.update_progress)

            if self.download_type.get() == "video":
                # 取得選擇的品質
                quality_str = self.quality_combobox.get()
                resolution = quality_str.split()[0]
                format = re.findall(r"/(\w+)", quality_str)[0]
                if (int(resolution.replace("p","")) < 720):
                    stream  = yt.streams.filter(progressive=True, resolution=resolution).first()
                else:
                    video_stream = yt.streams.filter(resolution=resolution).first()
                    video_path = video_stream.download(output_path="downloads/", filename="temp_video."+str(format))
                    audio_stream = yt.streams.filter(only_audio=True).first()
                    audio_path = audio_stream.download(output_path="downloads/", filename="temp_audio."+str(format))

                    output_path = self.save_path.get() + "/" + self.sanitize_filename(yt.title) + ".mp4"
                    cmd = [
                        ".\\ffmpeg",
                        # r"C:\Users\dmc95\Downloads\ffmpeg-2025-02-13-git-19a2d26177-essentials_build\ffmpeg-2025-02-13-git-19a2d26177-essentials_build\bin\ffmpeg.exe",
                        "-i", video_path,
                        "-i", audio_path,
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-strict", "experimental",
                        output_path
                    ]

                    subprocess.run(cmd, shell=True)
                    messagebox.showinfo("成功", "下載完成！")
                    os.remove(video_path)
                    os.remove(audio_path)

                    return
            else:
                stream = yt.streams.get_audio_only()

            # 下載檔案
            out_file = stream.download(output_path=self.save_path.get())

            # 如果是音訊，將檔案重新命名為mp3
            if self.download_type.get() == "audio":
                base, ext = os.path.splitext(out_file)
                new_file = base + '.mp3'
                os.rename(out_file, new_file)

            messagebox.showinfo("成功", "下載完成！")

        except Exception as e:
            messagebox.showerror("錯誤", f"下載失敗: {str(e)}")

        finally:
            self.download_button['state'] = 'normal'
            self.progress['value'] = 0
            self.status_label['text'] = ""


if __name__ == "__main__":
    root = tk.Tk()
    app = YouTubeDownloader(root)
    root.mainloop()