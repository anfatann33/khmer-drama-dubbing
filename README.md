# Khmer Drama AI Studio V4 — Free Edition

Flask website for **authorized MP4 video upload or direct HTTPS MP4 import → audio transcription/translation → Khmer TTS dubbing → MP4/SRT/JSON export**. Supports automatic source-language detection and English, Chinese, Korean, Japanese, Thai, Vietnamese, French, Spanish. Language identification, translation, speaker labels and timings use the Gemini API; dubbing uses gTTS and FFmpeg.

## Deploy on existing GitHub / Render

1. Extract the ZIP and upload the **contents** of `khmer_drama_v4` into the **root** of your existing GitHub repository, replacing `app.py`, `Dockerfile`, `requirements.txt`, `.gitignore`, `README.md`.
2. Keep Render **Docker** environment, using repository's `Dockerfile`.
3. Set Render Environment variables:
   - `GEMINI_API_KEY` = your private Gemini API key. **Never paste the key into GitHub.**
   - `GEMINI_MODEL` = an audio-capable Gemini model actually available to your API key, e.g. `gemini-2.5-flash` **only if listed in your account**. Model availability varies; check Google AI Studio / API model listing if 404 occurs.
   - `ALLOWED_VIDEO_HOSTS` = comma-separated exact hostnames you trust and are authorized to download from, e.g. `cdn.example.org,media.example.org`. No `https://` prefix. Leave unset to disable all URL downloads. URLs must be direct public HTTPS `.mp4` links from an allowed hostname. **No player-page scraping, redirects, login, VIP, DRM, playlist extraction or paywall bypass.**
4. Commit files; Render Auto Deploy or **Manual Deploy → Deploy latest commit**.
5. Check `/health`, then test a **10–20 second MP4** with clear English or Chinese speech.

## Limitations / important honesty

- **Not verified end-to-end** with your Gemini account, Render service or live TTS network. Python syntax and Flask route smoke tests are provided/checked during packaging.
- **Free-tier availability varies.** Render Free may sleep, time out, or run out of memory; Gemini quota may be exhausted; gTTS needs internet and service support for Khmer.
- No true lip movement sync, voice cloning, distinct natural male/female actors, or emotional voice acting. Male/female setting only adjusts pitch, based on Gemini's uncertain gender estimate.
- Timestamps are Gemini estimates. Audio is speed-adjusted up to 2x, then trimmed to each segment's allotted time. Translation may be cut off or overlap.
- Original speech remains faintly audible behind the dubbed audio. No music/speech source separation.
- Up to **5 uploaded episodes** processed sequentially by browser, **90 seconds each**; direct URL supports **one** episode at a time. Not full-series batch download from drama sites.
- MP4 only, max 45 MB uploads / 40 MB remote downloads; 5 requests/hour per IP.
- Keep API key private. For a publicly accessible deployment, add real user authentication before using it with untrusted users; rate limits are only a basic safeguard.

## Run locally

```bash
pip install -r requirements.txt
# Install ffmpeg and ffprobe on PATH
export GEMINI_API_KEY='YOUR_KEY'
export GEMINI_MODEL='MODEL_AVAILABLE_TO_YOUR_KEY'
python app.py
```

## API

- `GET /` user interface
- `GET /health` status without exposing secrets
- `POST /process` multipart form: `video` (MP4) **or** `url` (HTTPS direct MP4), `language` (`auto|en|zh|ko|ja|th|vi|fr|es`), `male` (`low|normal`), `female` (`high|normal`). Returns ZIP containing `dubbed.mp4`, `khmer_subtitles.srt`, `transcript.json`.
