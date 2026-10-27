# Khmer Drama AI Studio V4.7 — Gemini Only

## What is supported
- Upload MP4, or paste a public **YouTube, TikTok, or Facebook** video link and attempt import using `yt-dlp` (only where downloading and reuse are permitted).
- Direct public HTTPS `.mp4` links from exact hosts in `ALLOWED_VIDEO_HOSTS`.
- Episode HTML pages from exact hosts in `ALLOWED_PAGE_HOSTS` **only when the page explicitly provides a downloadable MP4 anchor**, and the MP4 host is allowlisted.
- Gemini speech transcription/Khmer translation, gTTS Khmer voice (subject to availability), MP4/SRT/JSON ZIP export.

## What is NOT supported
- **Hongguo series/detail/player links are not automatically downloadable.** A link to a player is not a media download URL. This build does not bypass VIP, DRM, paywalls, logins, or platform restrictions.
- Not all YouTube/TikTok/Facebook links work. Platform changes, geo restrictions and login requirements may block imports.
- A URL imports **one** video, not a full series. Upload mode supports up to 5 episodes.
- Videos must be <=90 seconds and <=40 MB. Free Render may time out. Source downloads may be restricted by platform terms or copyright.
- Voice uses gTTS (not Gemini TTS), and true lip-sync is not implemented.

## Deploy to GitHub and Render
1. Upload `app.py`, `requirements.txt`, `Dockerfile`, and `README.md` to repository root, replacing old versions.
2. In Render set `GEMINI_API_KEY` (secret), `GEMINI_MODEL=gemini-2.5-flash` (verify model availability); optionally `GEMINI_FALLBACK_MODEL`.
3. Optional `ALLOWED_VIDEO_HOSTS=cdn.example.com` and `ALLOWED_PAGE_HOSTS=episodes.example.com` for authorized direct MP4 and download pages. Do **not** include `https://`.
4. Deploy latest commit and check `/health` reports version `4.7`.
5. Test first with a short MP4 you own, then with a short public platform video you are permitted to download and translate.

## Security and operational notes
- The public platform importer is limited to known platform domains; it does not accept arbitrary yt-dlp extractors or login cookies. Platform redirects and extracted media URLs are controlled by third-party yt-dlp; do not expose this service publicly without stronger network egress isolation and authentication.
- DNS checks are not a complete SSRF defense against DNS rebinding. For production use, restrict outbound access at network level.
- Files are processed in a temporary directory and deleted when the response completes. Rate limiting uses in-memory storage (resets on restart).
- Gemini 503 retry is best-effort; quotas and 429 errors still apply.
