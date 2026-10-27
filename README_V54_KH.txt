Khmer Drama AI Studio V5.4 - Safe Stage Diagnostics

Changes:
- Go Short Drama CLI now marks SESSION_INIT, METADATA, and MEDIA failure stages.
- Python classifies these stages without exposing raw TikTok response, cookie, or signed URLs.
- Keeps V5.3 features and Render Docker deployment.

Deploy: replace app.py AND tiktok-crawler/cmd/tiktok_crawler/main.go on GitHub.
A new Docker build is necessary; replacing only app.py will NOT enable stage markers.
Keep TIKTOK_COOKIES_B64 and other secrets in Render Environment only.

IMPORTANT: This is a diagnostic improvement, NOT a proven fix for TikTok
Short Drama downloads. A live Render test is still required.
