Khmer Drama AI Studio V5.1 (Private / Render Free)

1. Extract ZIP and upload ALL contents to GitHub repository root, including tiktok-crawler folder and Dockerfile. Do not upload this ZIP directly.
2. In Render Environment keep GEMINI_API_KEY, GEMINI_MODEL and APP_PASSWORD.
3. OPTIONAL: TIKTOK_COOKIES_B64 = base64 of your own authorized TikTok cookies.txt file (Netscape cookie-jar or raw Cookie header). This is a SECRET, not an API key. Never put it in GitHub, chat, screenshots, or public logs.
4. To encode your local cookies.txt on Windows PowerShell (only on your own PC):
   [Convert]::ToBase64String([IO.File]::ReadAllBytes('C:\path\to\cookies.txt'))
   Copy the output into Render Environment TIKTOK_COOKIES_B64, not into GitHub.
5. The app creates a temporary private cookie file (0600) only while a job runs. Crawler receives -cookies-file path, not cookie contents. The file is removed when processing finishes.
6. Cookies are account credentials. Only use a session you control and are authorized to use. Do not share it with other users. If leaked, revoke TikTok sessions and rotate credentials.
7. V5.1 does not bypass DRM/paywalls, and cookies do not guarantee downloading: TikTok may reject Render's IP, expire the session, or change its APIs.
8. A working browser playback alone does not guarantee that server-side downloading is permitted or possible.
9. Render Free is ephemeral. It may sleep and has limited resources. Test one <=90 second authorized episode first.
10. V5.1 does not include automatic cookie extraction from your browser. Browser sessions must not be uploaded via public app forms.
