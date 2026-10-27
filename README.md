# Khmer Drama AI Studio V4.2 — Authorized Episode Page Import

Based on V4.1. This is a conservative, **explicit download-link-only** page resolver; it does not scrape video players, decode HLS, use browser cookies, bypass DRM or unlock VIP episodes.

## Deploy
Replace root `app.py`, `requirements.txt`, `Dockerfile`, and `README.md` in your existing GitHub repo; commit; Render redeploys.

## Render Environment
- `GEMINI_API_KEY` — existing secret; never share it.
- `GEMINI_MODEL` — a verified `generateContent` model ID accessible to your key (not a Live-only model).
- `ALLOWED_VIDEO_HOSTS` — comma-separated **exact HTTPS hostnames** serving MP4 files with download permission (example: `cdn.yourdomain.com`).
- `ALLOWED_PAGE_HOSTS` — comma-separated **exact HTTPS hostnames** of episode pages you are permitted to import (example: `episodes.yourdomain.com`).

No wildcard hosts. No host is allowed by default. The page resolver follows no redirects, limits HTML to 512 KB, blocks private IPs, and only accepts an `<a download href="...mp4">` or `<a rel="download" href="...mp4">` link whose target host is explicitly in `ALLOWED_VIDEO_HOSTS`. A page with multiple qualifying links must be handled using a single direct MP4 URL. Do not add hosts unless you are authorized to download from them.

## Capabilities and limitations
- One direct MP4 or authorized page URL per job; 1–5 MP4 file uploads. URL mode is one episode only.
- Gemini translates source audio into Khmer timestamps. gTTS synthesizes Khmer (network service, variable quality/availability). Pitch adjustment approximates male/female voices.
- MP4 + SRT + JSON output, maximum 90 seconds per episode; MP4 URL maximum 40 MB.
- **Hongguo player URLs do not have a known explicit authorized MP4 download link**. This feature does not make Hongguo import work automatically. Playback is not download permission.
- No true face-based lip sync, no voice cloning, no guaranteed production reliability on Render Free.
- Test with a legally downloadable public MP4 and an HTML page explicitly offering that MP4 for download.

## Diagnostics
`/health` displays the deployed version, selected model, and whether a key is configured (not the key itself).
