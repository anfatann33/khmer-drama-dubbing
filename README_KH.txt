V4.9 TikTok Crawler integration (experimental)

Upload all files including the tiktok-crawler folder to GitHub. Render must use Docker deployment.
The Docker build downloads Go modules and builds the crawler. Render network access is required.
TikTok Short Drama URLs use the bundled Go crawler. Normal supported platform URLs still use yt-dlp.
Only public, authorized downloads. No login, cookie, paywall or DRM bypass.
This build has passed Python syntax checks, NOT a live TikTok download test.
Video limit: 90 seconds / 40 MB; source limitations and Render resources still apply.
Keep GEMINI_API_KEY in Render Environment, never in GitHub.
