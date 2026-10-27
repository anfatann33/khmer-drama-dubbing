# Khmer Drama AI Studio V4.1 (Free-first)

Flask + Gemini translation + free gTTS Khmer speech + FFmpeg.

## Render Docker deployment

Replace the existing repository root files `app.py`, `requirements.txt`, `Dockerfile` with these files. Commit. Render Docker service deploys latest commit.

Environment variables:
- `GEMINI_API_KEY`: secret key from Google AI Studio (required).
- `GEMINI_MODEL`: `gemini-3.8-flash` **only if** your API key can call that exact model via the standard `generateContent` API. The app defaults to this name, but availability and free quota vary. If you get a 404, inspect your actual available model IDs and choose a compatible text/multimodal generateContent model.
- `ALLOWED_VIDEO_HOSTS`: optional comma-separated exact public HTTPS hosts you control or are authorized to download from. Without this, direct URL import is disabled. MP4 upload still works.

## Supported
- MP4 uploads (up to five), or one direct authorized HTTPS MP4 URL, not a webpage or DRM stream.
- Auto language recognition or select English/Chinese/Korean/Thai/Japanese/Vietnamese/French/Spanish.
- Gemini translates spoken audio into timestamped Khmer transcript.
- gTTS (`km`) generates Khmer speech; pitch adjustment for estimated male/female speaker. **gTTS is an external network service and can fail or throttle.**
- Download ZIP with MP4, SRT and JSON.

## Not supported
- No Hongguo player page scraping, no VIP/DRM bypass, no direct video-page downloading, no batch URL episode discovery.
- No real mouth lip-sync, no reliable speaker-to-face matching, no guaranteed emotion or voice quality, no background music separation.
- Render Free may run out of memory or timeout. Max 90 seconds and 40 MB direct download per video. No guaranteed end-to-end reliability; integration testing with your Gemini account is required.

## Check
Visit `/health` to confirm deployed version, model and API key presence (not the key itself).
Start with one 10-20 second MP4 in English or Mandarin. Never paste your API key in screenshots.
