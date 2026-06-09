# Use the Python 3.11 slim image.
FROM python:3.11-slim

# Install FFmpeg and build tools required by discord.py voice dependencies.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir discord.py[voice] yt-dlp

COPY . .

CMD ["python", "main.py"]
