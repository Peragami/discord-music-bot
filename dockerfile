# Build stage: install dependencies with build tools
FROM python:3.11-slim AS builder

RUN apt-get update --allow-releaseinfo-change && apt-get install -y \
    gcc \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "discord.py[voice]" "yt-dlp[default]"

# Runtime stage: only what's needed to run
FROM python:3.11-slim

RUN apt-get update --allow-releaseinfo-change && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app
COPY . .

CMD ["python", "main.py"]
