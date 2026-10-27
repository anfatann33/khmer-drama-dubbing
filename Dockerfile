# Build the bundled TikTok Crawler from the user-provided Go source.
FROM golang:1.25-bookworm AS crawler-build
WORKDIR /src
COPY tiktok-crawler/go.mod tiktok-crawler/go.sum ./
RUN go mod download
COPY tiktok-crawler/ ./
RUN CGO_ENABLED=0 go build -trimpath -o /out/tiktok_crawler ./cmd/tiktok_crawler

FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-core ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=crawler-build /out/tiktok_crawler /usr/local/bin/tiktok_crawler
COPY app.py .
ENV PORT=10000
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --timeout 600 app:app"]
