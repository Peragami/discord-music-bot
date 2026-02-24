# Python 3.11のスリム版を使用
FROM python:3.11-slim

# FFmpeg、ビルドに必要なツール(PyNaCl用)をインストール
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリ設定
WORKDIR /app

# ライブラリをインストール（PyNaClを追加）
RUN pip install --no-cache-dir discord.py[voice] yt-dlp

# ソースコードをコピー
COPY . .

# 実行
CMD ["python", "main.py"]
