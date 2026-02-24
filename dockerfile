# Python 3.11のスリム版を使用
FROM python:3.11-slim

# FFmpegと依存関係をインストール
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリ設定
WORKDIR /app

# ライブラリをインストール
# yt-dlpは頻繁に更新されるため、キャッシュを使わず最新を入れるのがコツ
RUN pip install --no-cache-dir discord.py yt-dlp

# ソースコードをコピー
COPY . .

# 実行
CMD ["python", "main.py"]
