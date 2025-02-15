# Youtube_Download_Tool
Youtuber Download 拒絕每次下載音樂都被要求註冊莫名其妙的會員


## 使用方式
1. 安裝Python
2. 安裝套件 (使用 pip install requirement.txt裡面的套件)
3. 運行

## 問題解決

### 如果下載發生錯誤可以怎麼做？
* /download有包含不需要的音訊視訊緩存，若異常終止，請手動刪除
* Pytube套件因為有異常，所以後續我使用了pytubefix這個套件，但不確定後續工具是否會被取代。
* ffmpeg.exe有機率異常，如果發現檔案刪不掉，去工作管理員把ffmpeg.exe終止工作
* ffmpeg.exe放置於當前目錄，如果想本地環境使用則須修改cmd變數中的參數，並記得加入環境變數