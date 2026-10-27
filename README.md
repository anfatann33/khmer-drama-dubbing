# Khmer Drama AI Studio V3 (Free prototype)

Features: upload up to 5 numbered MP4 episodes, choose a contiguous episode range, direct authorized HTTPS MP4 URL import from an allowlisted host, Gemini speech segmentation/Khmer translation, gTTS Khmer voice with basic pitch profiles, approximate dialogue timing, MP4 and SRT output.

## Limits
- No VIP/paywall/DRM bypass, no scraping drama detail pages.
- No AI lip movement editing. Video is copied unchanged; only audio is aligned approximately.
- Speaker gender identification is estimated and pitch processing is not real male/female actor casting.
- One 90-second, 45MB max upload per request; 5 uploads per browser batch; 5 processing requests per IP/hour.
- Gemini model availability and free quota vary by account. Set `GEMINI_MODEL` to a model confirmed available to your API key. Default `gemini-3.8-flash` is based on the error shown in the user's account and has not been independently tested here.
- gTTS requires internet and Khmer language support; if service declines Khmer, TTS will fail. Check service before use.
- Free Render 512MB RAM and request timeouts make this suitable only for small experiments. Do not promise production-quality episodes.
- API key is server-side only. Use permitted content and permission for translation/republication.

## Deploy
1. Replace `app.py`, `requirements.txt`, `Dockerfile` in existing GitHub repository. Commit.
2. Render: keep existing Docker web service and `GEMINI_API_KEY`; optionally set `GEMINI_MODEL` to an available text model.
3. Optional `ALLOWED_VIDEO_HOSTS=cdn.your-authorized-domain.com` for direct HTTPS MP4 URL import. This is intentionally disabled by default to reduce SSRF risk.
4. Render auto deploy or Manual Deploy -> Deploy latest commit.
5. Test with a 10-second MP4 that you own. If model 404 occurs, list your available models and set `GEMINI_MODEL` accordingly.

Note: For a real multi-episode lip-sync workflow, use a background queue, durable storage, reliable diarization and a GPU lip-sync model; these are not feasible as promised features on this free Render instance.
