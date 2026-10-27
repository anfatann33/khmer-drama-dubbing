import base64
import binascii
import ipaddress
import hashlib
import hmac
import resource
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse, urljoin
from html.parser import HTMLParser

import requests
from flask import Flask, jsonify, render_template_string, request, send_file, session, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import TooManyRequests
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from gtts import gTTS
from pydub import AudioSegment

app = Flask(__name__)
# Secret derives from Render APP_PASSWORD; it is never sent to the client.
_password = os.getenv('APP_PASSWORD', '')
if not _password:
    raise RuntimeError('APP_PASSWORD must be configured in Render Environment before starting V5.0')
app.secret_key = hashlib.sha256(('KhmerDramaAIStudioV5/session/v1:' + _password).encode('utf-8')).digest()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True,
                  SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=12 * 60 * 60,
                  MAX_CONTENT_LENGTH=45 * 1024 * 1024)
limiter = Limiter(get_remote_address, app=app, default_limits=['20 per hour'], storage_uri='memory://', headers_enabled=True)
MAX_SECONDS = 90
MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024
SUPPORTED_PLATFORMS = {"youtube.com": "YouTube", "youtu.be": "YouTube", "tiktok.com": "TikTok", "facebook.com": "Facebook", "fb.watch": "Facebook"}
MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
FALLBACK_MODEL = os.getenv('GEMINI_FALLBACK_MODEL', '').strip()
RETRY_DELAYS = (3, 7)  # bounded retries for temporary Gemini 503 only
LANGUAGES = {'auto': 'Automatically identify the spoken language', 'en': 'English', 'zh': 'Mandarin Chinese', 'ko': 'Korean', 'ja': 'Japanese', 'th': 'Thai', 'vi': 'Vietnamese', 'fr': 'French', 'es': 'Spanish'}

PAGE = '''<!doctype html><html lang="km"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Khmer Drama AI Studio V5.4</title><style>body{margin:0;padding:20px;background:#0b1220;color:#eaf0ff;font:15px Arial,sans-serif}main{max-width:850px;margin:auto}section{background:#1c273a;padding:22px;margin:16px 0;border-radius:16px}h1{font-size:28px}label{display:block;margin:14px 0 6px}input,select,textarea,button{font:inherit;padding:11px;border-radius:8px;box-sizing:border-box}input[type=url],input[type=text],select,textarea{width:100%;background:#0d1728;color:#fff;border:1px solid #50617d}input[type=number]{width:100px;background:#0d1728;color:#fff;border:1px solid #50617d}button{background:#7558e8;color:white;border:0;cursor:pointer;font-weight:bold}button:disabled{opacity:.5}.hint{color:#a9b9d3;font-size:13px;line-height:1.5}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.error{color:#ffb5b5}a{color:#b7c8ff}#status{white-space:pre-wrap;line-height:1.5}</style></head><body><main><h1>🎬 Khmer Drama AI Studio V5.4</h1><p>Multi-language → Khmer · Free Edition · Authorized downloads only</p><form method="post" action="/logout"><button type="submit" style="background:#34445d">Log out</button></form><section><h2>1. Video source</h2><label>Upload MP4 episodes (up to 5 files)</label><input id="files" type="file" accept="video/mp4" multiple><p class="hint">Name files 001.mp4, 002.mp4, etc. Upload OR URL; do not use both.</p><label>OR public YouTube / TikTok / Facebook link, authorized MP4, or episode page</label><input id="url" type="url" placeholder="https://your-authorized-host.com/episode.mp4"><p class="hint">Public YouTube, ordinary TikTok videos and Facebook links are attempted with yt-dlp where permitted. TikTok Short Drama episode pages are attempted with the bundled crawler; TikTok may require a valid authorized session configured privately by the owner, so some links cannot be downloaded. Hongguo and other Chinese drama sites are recognized but require an explicitly offered downloadable MP4 link. No VIP, DRM, login, cookies or paywall bypass. Not all links will work. Only process videos you have permission to use.</p><label><input id="permission" type="checkbox"> I have permission to download and translate this video.</label><div class="grid"><div><label>From episode</label><input id="start" type="number" min="1" value="1"></div><div><label>To episode</label><input id="end" type="number" min="1" value="1"></div></div><p class="hint">For uploads, episode numbers correspond to sorted filenames. URL mode accepts one MP4 episode only.</p></section><section><h2>2. Translation & voices</h2><label>Original spoken language</label><select id="language"><option value="auto">Auto detect</option><option value="en">English</option><option value="zh">Chinese / Mandarin</option><option value="ko">Korean</option><option value="ja">Japanese</option><option value="th">Thai</option><option value="vi">Vietnamese</option><option value="fr">French</option><option value="es">Spanish</option></select><label>Target language</label><input type="text" value="Khmer (ភាសាខ្មែរ)" readonly><div class="grid"><div><label>Male voice (estimated)</label><select id="male"><option value="low">Lower pitch</option><option value="normal">Normal pitch</option></select></div><div><label>Female voice (estimated)</label><select id="female"><option value="high">Higher pitch</option><option value="normal">Normal pitch</option></select></div></div><p class="hint">Speaker and gender classification are estimates. Free Khmer gTTS voice with pitch adjustments. No Gemini TTS quota used. Gender estimation can be wrong; no voice cloning, emotion control, or visual lip-sync.</p></section><section><h2>3. Translate, dub & export</h2><p class="hint">Step 1: check local crawler and cookie setup. This does not contact TikTok.</p><button type="button" onclick="checkCrawler()" style="background:#34445d">Check TikTok Setup</button><p id="diagnostic" role="status"></p><button id="go" onclick="run()">Download (if URL) + Translate + Khmer Dub</button><p id="status" role="status"></p><div id="results"></div><p class="hint">Each episode: maximum 90 seconds. Processing may fail on free hosting due to quotas, timeout or memory.</p></section></main><script>
async function checkCrawler(){const el=document.getElementById('diagnostic');el.textContent='Checking...';try{const r=await fetch('/diagnostics/tiktok',{cache:'no-store'});if(!r.ok){el.textContent='Setup check failed (HTTP '+r.status+')';return;}const x=await r.json();el.textContent='Crawler: '+x.crawler_binary+' | Session: '+x.session+' | TikTok network: NOT TESTED';}catch(e){el.textContent='Unable to run setup check';}}
async function run(){const files=[...document.getElementById('files').files].sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}));const url=document.getElementById('url').value.trim();const start=Number(document.getElementById('start').value),end=Number(document.getElementById('end').value);const status=document.getElementById('status'),out=document.getElementById('results'),btn=document.getElementById('go');out.replaceChildren();if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end<start||end-start+1>5){status.textContent='Select 1–5 episodes in a valid range.';return}if((files.length>0)===(url.length>0)){status.textContent='Provide MP4 uploads OR one authorized URL.';return}if(files.length&&files.length<end){status.textContent='Not enough uploaded episodes for selected range.';return}if(url&&(start!==1||end!==1)){status.textContent='URL import supports one episode only (1 to 1).';return}if(!document.getElementById('permission').checked){status.textContent='Please confirm that you have permission to use this video.';return}btn.disabled=true;try{for(let i=start;i<=end;i++){status.textContent='Processing episode '+i+'... This can take several minutes.';const fd=new FormData();if(files.length)fd.append('video',files[i-1]);else fd.append('url',url);fd.append('authorized','yes');fd.append('language',document.getElementById('language').value);fd.append('male',document.getElementById('male').value);fd.append('female',document.getElementById('female').value);const response=await fetch('/process',{method:'POST',body:fd});if(!response.ok){let err=await response.text();try{err=JSON.parse(err).error||err}catch{}if(response.status===429){const wait=response.headers.get('Retry-After');err+=' Please wait'+(wait?' '+wait+' seconds':'')+' before retrying.'}throw Error('Episode '+i+': '+err)}const blob=await response.blob(),href=URL.createObjectURL(blob),a=document.createElement('a');a.href=href;a.download='khmer_episode_'+String(i).padStart(3,'0')+'.zip';a.textContent='⬇ Download episode '+i+' (MP4 + SRT + JSON)';a.style.display='block';a.style.margin='10px 0';out.append(a)}status.textContent='Finished. Use the download links below.'}catch(e){status.textContent='Error: '+e.message;status.className='error'}finally{btn.disabled=false}}
</script></body></html>'''


def run_cmd(*args, timeout=150):
    p = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('Media processing error: ' + p.stderr[-350:])
    return p.stdout


def video_duration(path):
    return float(run_cmd('ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path), timeout=20).strip())


class DownloadLinkParser(HTMLParser):
    """Collect only explicit downloadable MP4 anchors, not player media streams."""
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'a':
            return
        attrs = dict(attrs)
        href = attrs.get('href', '')
        if not href:
            return
        # Require the page author to explicitly mark a link as downloadable.
        rel = str(attrs.get('rel', '')).lower().split()
        if 'download' in attrs or 'download' in rel:
            self.links.append(href)


def resolve_authorized_page(url):
    """Return a public HTTPS MP4 URL explicitly marked for download on an allowed page."""
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Episode page must be a public HTTPS URL on port 443')
    page_hosts = {h.strip().lower() for h in os.getenv('ALLOWED_PAGE_HOSTS', '').split(',') if h.strip()}
    if parsed.hostname.lower() not in page_hosts:
        raise ValueError('Episode page host is not authorized. Configure ALLOWED_PAGE_HOSTS in Render.')
    check_public_host(parsed.hostname)
    with requests.get(url, timeout=(8, 15), stream=True, allow_redirects=False,
                      headers={'User-Agent': 'KhmerDramaAIStudio/4.2'}) as response:
        if response.status_code != 200:
            raise ValueError(f'Episode page returned HTTP {response.status_code}; redirects are not followed')
        if response.headers.get('Content-Type', '').split(';')[0].strip().lower() not in ('text/html', 'application/xhtml+xml'):
            raise ValueError('Episode URL did not return an HTML page')
        size = 0
        chunks = []
        for chunk in response.iter_content(chunk_size=16384):
            size += len(chunk)
            if size > 512 * 1024:
                raise ValueError('Episode page exceeds 512 KB inspection limit')
            chunks.append(chunk)
    parser = DownloadLinkParser()
    parser.feed(b''.join(chunks).decode('utf-8', errors='replace'))
    valid = []
    for href in parser.links[:30]:
        candidate = urljoin(url, href)
        try:
            allowed_url(candidate)
            valid.append(candidate)
        except (ValueError, OSError):
            continue
    if len(valid) == 1:
        return valid[0]
    if len(valid) > 1:
        raise ValueError('Multiple authorized MP4 downloads found; use one direct MP4 URL')
    raise ValueError('No explicitly authorized MP4 download link found on this episode page. Playback alone is not a download permission.')


def check_public_host(host):
    ips = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not ips or any(not ipaddress.ip_address(x[4][0]).is_global for x in ips):
        raise ValueError('Private or reserved IP addresses are blocked')


def allowed_url(url):
    p = urlparse(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Only public HTTPS URLs on port 443 are supported')
    if not p.path.lower().endswith('.mp4'):
        raise ValueError('Use a direct .mp4 URL, not a video player or drama page')
    hosts = [x.strip().lower() for x in os.getenv('ALLOWED_VIDEO_HOSTS', '').split(',') if x.strip()]
    if p.hostname.lower() not in hosts:
        raise ValueError('Video host is not authorized. Add its exact hostname to ALLOWED_VIDEO_HOSTS in Render.')
    check_public_host(p.hostname)
    return p


def platform_name(url):
    """Only enable known, public platform extractors; never a generic arbitrary URL."""
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('A public HTTPS video URL is required')
    host = parsed.hostname.lower().rstrip('.')
    for domain, name in SUPPORTED_PLATFORMS.items():
        if host == domain or host.endswith('.' + domain):
            check_public_host(host)
            return name
    return None


def tiktok_cookie_check(cookie_bytes):
    """Return only non-secret cookie format and msToken presence diagnostics."""
    try:
        contents = cookie_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('TIKTOK_COOKIE_ENCODING: Cookie file is not UTF-8 text')
    rows = [row.strip() for row in contents.splitlines() if row.strip()]
    valid_rows = 0
    has_token = False
    for row in rows:
        if row.startswith('#HttpOnly_'):
            row = row[len('#HttpOnly_'):]
        elif row.startswith('#'):
            continue
        fields = row.split('\t')
        if len(fields) != 7:
            continue
        domain, _, _, _, _, name, value = fields
        if domain.lower().lstrip('.').endswith('tiktok.com') and (domain.lower().lstrip('.') == 'tiktok.com' or domain.lower().lstrip('.').endswith('.tiktok.com')):
            valid_rows += 1
            if name == 'msToken' and value.strip():
                has_token = True
    if not valid_rows:
        raise ValueError('TIKTOK_COOKIE_FORMAT: No TikTok Netscape cookie rows found in configured file')
    if not has_token:
        raise ValueError('TIKTOK_MSTOKEN_MISSING: Cookie file has no nonempty msToken entry')
    return valid_rows


def classify_tiktok_crawler_error(stderr, stdout):
    """Allowlist-only diagnostic categories; never include raw crawler output."""
    output = (stderr + '\n' + stdout).lower()
    # These categories are grounded in actual errors in bundled shortdrama/resolver.go.
    if 'fetch short drama episode:' in output:
        if 'status 403' in output or 'forbidden' in output:
            return 'TIKTOK_EPISODE_FETCH_403'
        if 'status 429' in output:
            return 'TIKTOK_EPISODE_FETCH_429'
        return 'TIKTOK_EPISODE_FETCH_FAILED'
    if 'decode short drama episode:' in output:
        return 'TIKTOK_EPISODE_JSON_FAILED'
    if 'tiktok short drama returned status' in output:
        return 'TIKTOK_EPISODE_API_STATUS'
    if 'returned short drama metadata but no downloadable media profiles' in output:
        return 'TIKTOK_NO_MEDIA_PROFILES'
    if 'resolve short drama playback metadata:' in output:
        if 'empty signed response' in output:
            return 'TIKTOK_SIGNED_RESPONSE_EMPTY'
        if 'status 403' in output or 'forbidden' in output:
            return 'TIKTOK_SIGNED_DETAIL_403'
        if 'status 429' in output:
            return 'TIKTOK_SIGNED_DETAIL_429'
        if 'returned status' in output:
            return 'TIKTOK_SIGNED_DETAIL_API_STATUS'
        return 'TIKTOK_SIGNED_DETAIL_FAILED'
    if 'tiktok item detail returned status' in output:
        return 'TIKTOK_SIGNED_DETAIL_API_STATUS'
    if 'no downloadable media profiles' in output:
        return 'TIKTOK_NO_MEDIA_PROFILES'
    if 'valid mstoken cookie' in output or 'mstoken cookie' in output and ('requires' in output or 'missing' in output):
        return 'TIKTOK_CRAWLER_MSTOKEN_MISSING'
    if 'empty signed response' in output:
        return 'TIKTOK_EMPTY_SIGNED_RESPONSE'
    if 'status 403' in output or 'http 403' in output or 'forbidden' in output:
        return 'TIKTOK_HTTP_403'
    if 'status 401' in output or 'http 401' in output or 'unauthorized' in output:
        return 'TIKTOK_HTTP_401'
    if 'status 429' in output or 'http 429' in output or 'too many requests' in output:
        return 'TIKTOK_HTTP_429'
    if 'no episode item' in output or 'no episode' in output:
        return 'TIKTOK_NO_EPISODE_ITEM'
    if 'unexpected end of json' in output or 'invalid character' in output or 'cannot unmarshal' in output:
        return 'TIKTOK_METADATA_INVALID_JSON'
    if 'timeout' in output or 'deadline exceeded' in output or 'timed out' in output:
        return 'TIKTOK_NETWORK_TIMEOUT'
    if 'no such host' in output or 'dns' in output or 'name resolution' in output:
        return 'TIKTOK_DNS_FAILURE'
    if 'connection refused' in output or 'connection reset' in output or 'network is unreachable' in output:
        return 'TIKTOK_NETWORK_FAILURE'
    if 'cookie' in output and ('invalid' in output or 'parse' in output or 'load' in output):
        return 'TIKTOK_COOKIE_PARSE_FAILED'
    if 'download' in output and ('failed' in output or 'error' in output):
        return 'TIKTOK_MEDIA_DOWNLOAD_FAILED'
    # Stage markers are emitted by our bundled Go CLI. These are constant
    # strings and cannot expose cookies, signed URLs, or HTTP response bodies.
    if 'kd_stage_session_init:' in output:
        return 'TIKTOK_SESSION_INIT_FAILED'
    if 'kd_stage_metadata:' in output:
        return 'TIKTOK_METADATA_STAGE_FAILED'
    if 'kd_stage_media:' in output:
        return 'TIKTOK_MEDIA_STAGE_FAILED'
    return 'TIKTOK_CRAWLER_UNKNOWN'


def download_shortdrama_with_crawler(url, dest):
    """Use bundled Go TikTok Crawler for public, authorized short-drama episodes."""
    parsed = urlparse(url)
    if not re.fullmatch(r'/shortdrama/episode/[0-9]+/[1-9][0-9]*/?', parsed.path):
        raise ValueError('Invalid TikTok Short Drama episode URL')
    binary = '/usr/local/bin/tiktok_crawler'
    if not os.path.isfile(binary):
        raise ValueError('TikTok Crawler binary missing. Deploy using the bundled Dockerfile.')
    # Strip URL query parameters; only the canonical episode URL is required.
    canonical = 'https://www.tiktok.com' + parsed.path
    command = [binary, '-output', str(dest), '-quality', '720p']
    # Optional owner-supplied TikTok session. Never pass cookies in argv, logs,
    # source code, or HTTP requests. The file is temporary and mode 0600.
    cookie_data = os.getenv('TIKTOK_COOKIES_B64', '').strip()
    if not cookie_data:
        raise ValueError('TIKTOK_COOKIE_NOT_CONFIGURED: Set TIKTOK_COOKIES_B64 in Render Environment')
    if cookie_data:
        if len(cookie_data) > 131072:
            raise ValueError('TikTok session configuration is too large')
        try:
            cookie_bytes = base64.b64decode(cookie_data, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError('Invalid TIKTOK_COOKIES_B64 encoding in Render Environment')
        if not cookie_bytes or len(cookie_bytes) > 98304:
            raise ValueError('TikTok session configuration has an invalid size')
        tiktok_cookie_check(cookie_bytes)
        cookie_path = dest.parent / '.tiktok_session.txt'
        fd = os.open(str(cookie_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'wb') as secret_file:
                secret_file.write(cookie_bytes)
        except Exception:
            cookie_path.unlink(missing_ok=True)
            raise
        command.extend(['-cookies-file', str(cookie_path)])
    command.append(canonical)
    def limit_child():
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_DOWNLOAD_BYTES, MAX_DOWNLOAD_BYTES))
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=110, cwd=str(dest.parent), preexec_fn=limit_child)
    except subprocess.TimeoutExpired:
        raise ValueError('TIKTOK_CRAWLER_TIMEOUT: Download exceeded 110 seconds on Render.')
    if result.returncode:
        # Crawler output may contain signed URLs, cookies, and sensitive headers.
        # Only emit a fixed diagnostic code derived from known, safe patterns.
        code = classify_tiktok_crawler_error(result.stderr or '', result.stdout or '')
        app.logger.warning('TikTok Crawler failed: diagnostic=%s exit_nonzero=true', code)
        raise ValueError('TikTok Crawler download failed. Diagnostic: ' + code + '. Share only this code for troubleshooting.')
    if not dest.is_file() or dest.stat().st_size == 0:
        raise ValueError('TIKTOK_NO_MP4_OUTPUT: Crawler exited without producing an MP4.')
    if dest.stat().st_size > MAX_DOWNLOAD_BYTES:
        raise ValueError('Downloaded episode exceeds the 40 MB limit')


def download_platform_video(url, dest):
    """Public, unprotected videos only; no cookies, credentials or generic extractors."""
    name = platform_name(url)
    if not name:
        raise ValueError('Not a supported public video platform')
    parsed = urlparse(url)
    if name == 'TikTok' and re.fullmatch(r'/shortdrama/episode/[0-9]+/[1-9][0-9]*/?', parsed.path):
        return download_shortdrama_with_crawler(url, dest)
    folder = dest.parent
    template = str(folder / 'platform.%(ext)s')
    command = ['yt-dlp', '--no-playlist', '--no-config', '--no-cache-dir',
               '--no-warnings', '--no-progress', '--no-call-home',
               '--socket-timeout', '15', '--retries', '1', '--fragment-retries', '1',
               '--max-filesize', '40M', '--match-filter', 'duration <= 90',
               '--format', 'best[ext=mp4][height<=720]/best[height<=720]/best',
               '--merge-output-format', 'mp4', '--output', template,
               '--', url]
    def limit_child():
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_DOWNLOAD_BYTES, MAX_DOWNLOAD_BYTES))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=110,
                                preexec_fn=limit_child, cwd=str(folder))
    except subprocess.TimeoutExpired:
        raise ValueError(f'{name}: Download timed out. Try a shorter public video.')
    if result.returncode:
        msg = (result.stderr or result.stdout)[-500:]
        if name == 'TikTok' and ('/foryou' in msg or 'Unsupported URL' in msg):
            raise ValueError('TikTok redirected the downloader to an unsupported page. This is not a bad copied link; this video cannot be imported by the current public extractor. If TikTok offers Save Video, upload that MP4 with permission.')
        raise ValueError(f'{name}: Cannot download this video. It may require login, be restricted, or be unsupported. {msg}')
    candidates = [x for x in folder.glob('platform.*') if x.suffix.lower() in ('.mp4', '.mkv', '.webm')]
    if len(candidates) != 1:
        raise ValueError(f'{name}: No single downloadable video was produced')
    candidate = candidates[0]
    if candidate.stat().st_size > MAX_DOWNLOAD_BYTES:
        raise ValueError('Video exceeds 40 MB limit')
    if candidate.suffix.lower() == '.mp4':
        candidate.rename(dest)
    else:
        run_cmd('ffmpeg', '-y', '-i', str(candidate), '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(dest), timeout=110)
    if dest.stat().st_size > MAX_DOWNLOAD_BYTES:
        raise ValueError('Converted video exceeds 40 MB limit')


def download_mp4(url, dest):
    allowed_url(url)
    with requests.get(url, stream=True, timeout=(8, 25), allow_redirects=False, headers={'User-Agent': 'KhmerDramaAIStudioV4/1.0'}) as response:
        if response.status_code != 200:
            raise ValueError('Video URL returned HTTP ' + str(response.status_code) + ' (redirects are not supported)')
        content_type = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
        if content_type not in ('video/mp4', 'application/octet-stream'):
            raise ValueError('URL did not return MP4 media (Content-Type: ' + content_type + ')')
        length = response.headers.get('Content-Length')
        if length and int(length) > MAX_DOWNLOAD_BYTES:
            raise ValueError('Video exceeds 40 MB download limit')
        size = 0
        with open(dest, 'wb') as output:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError('Video exceeds 40 MB download limit')
                output.write(chunk)


def generate_with_503_retry(client, upload, prompt):
    """Retry temporary 503 errors; optionally try a user-configured fallback model.

    No retry for 429 quota/rate-limit, authentication, invalid model or bad request.
    """
    models = [MODEL]
    if FALLBACK_MODEL and FALLBACK_MODEL != MODEL:
        models.append(FALLBACK_MODEL)
    for index, model in enumerate(models):
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                return client.models.generate_content(
                    model=model,
                    contents=[upload, prompt],
                    config=types.GenerateContentConfig(response_mime_type='application/json'),
                )
            except genai_errors.APIError as exc:
                code = getattr(exc, 'code', None)
                if code == 429:
                    raise RuntimeError('Gemini quota/rate limit (429). Wait for quota reset; automatic retry disabled.') from exc
                if code != 503:
                    raise RuntimeError(f'Gemini API error {code}: verify model access, key and API settings in Render logs.') from exc
                if attempt < len(RETRY_DELAYS):
                    delay = RETRY_DELAYS[attempt]
                    app.logger.warning('Gemini 503 on model %s; retrying after %ss (attempt %s)', model, delay, attempt + 1)
                    time.sleep(delay)
                else:
                    app.logger.warning('Gemini 503 persisted on model %s', model)
                    if index == len(models) - 1:
                        raise RuntimeError('Gemini 503: model is overloaded after retries. Try again later or configure GEMINI_FALLBACK_MODEL with an available compatible model.') from exc
                    app.logger.warning('Trying configured fallback model %s', models[index + 1])
    raise RuntimeError('No Gemini model was available')


def translate_audio(client, audio_path, length, language):
    upload = client.files.upload(file=str(audio_path))
    try:
        for _ in range(45):
            upload = client.files.get(name=upload.name)
            state = str(getattr(getattr(upload, 'state', None), 'name', ''))
            if state == 'ACTIVE':
                break
            if state == 'FAILED':
                raise RuntimeError('Gemini audio upload failed')
            time.sleep(2)
        else:
            raise RuntimeError('Gemini audio processing timed out')
        hint = LANGUAGES[language]
        prompt = (f'Transcribe speech from this audio. Source language: {hint}. Translate EVERY spoken utterance into natural conversational Khmer (Khmer script). '
                  'Identify speakers as speaker_1, speaker_2, etc. Estimate speaker gender from voice only as male/female/unknown, acknowledging uncertainty. '
                  'Return ONLY a JSON array, each item having start (seconds), end (seconds), speaker, gender, khmer. '
                  f'Timestamps must be relative to the audio, between 0 and {length:.2f} seconds. Keep each item short. Do not invent dialogue.')
        response = generate_with_503_retry(client, upload, prompt)
        try:
            parsed = json.loads(response.text)
        except (TypeError, ValueError):
            raise RuntimeError('Gemini did not return valid JSON; try a different GEMINI_MODEL')
        if isinstance(parsed, dict):
            parsed = parsed.get('segments', [])
        if not isinstance(parsed, list):
            raise RuntimeError('Gemini returned unexpected transcript format')
        segments = []
        for row in parsed[:120]:
            if not isinstance(row, dict):
                continue
            try:
                start = max(0.0, float(row['start']))
                end = min(length, float(row['end']))
                text = str(row['khmer']).strip()
                gender = str(row.get('gender', 'unknown')).lower()
                if gender not in ('male', 'female'):
                    gender = 'unknown'
                if end > start and text:
                    segments.append({'start': start, 'end': end, 'speaker': str(row.get('speaker', 'unknown'))[:40], 'gender': gender, 'khmer': text})
            except (ValueError, TypeError, KeyError):
                continue
        return sorted(segments, key=lambda row: row['start'])
    finally:
        try:
            client.files.delete(name=upload.name)
        except Exception:
            pass


def timestamp(seconds):
    ms = int(max(0, seconds) * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def dub_audio(segments, folder, length, male, female):
    timeline = AudioSegment.silent(duration=int(length * 1000) + 200, frame_rate=24000)
    for i, segment in enumerate(segments):
        speech = folder / f'speech_{i}.mp3'
        try:
            gTTS(text=segment['khmer'], lang='km').save(str(speech))
        except Exception as exc:
            raise RuntimeError('Khmer TTS failed (gTTS requires network and Khmer support): ' + str(exc))
        part = AudioSegment.from_file(speech).set_channels(1).set_frame_rate(24000)
        pitch = 0.86 if segment['gender'] == 'male' and male == 'low' else (1.14 if segment['gender'] == 'female' and female == 'high' else 1.0)
        if pitch != 1:
            part = part._spawn(part.raw_data, overrides={'frame_rate': int(part.frame_rate * pitch)}).set_frame_rate(24000)
        target_ms = max(1, int((segment['end'] - segment['start']) * 1000))
        if len(part) > target_ms and target_ms >= 150:
            speed = len(part) / target_ms
            if speed <= 2.0:
                original = folder / f'voice_{i}.wav'
                adjusted = folder / f'voice_adjusted_{i}.wav'
                part.export(original, format='wav')
                run_cmd('ffmpeg', '-y', '-i', str(original), '-filter:a', f'atempo={speed:.4f}', str(adjusted))
                part = AudioSegment.from_file(adjusted)
        timeline = timeline.overlay(part[:target_ms], position=int(segment['start'] * 1000))
    path = folder / 'khmer_voice.wav'
    timeline.export(path, format='wav')
    return path


LOGIN_PAGE = '''<!doctype html><html lang="km"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Khmer Drama AI Studio — Sign in</title><style>body{background:#0b1220;color:#eaf0ff;font:16px Arial,sans-serif;min-height:100vh;display:grid;place-items:center;margin:0}.card{background:#1c273a;padding:32px;border-radius:16px;width:min(380px,85vw)}input,button{box-sizing:border-box;width:100%;padding:13px;border-radius:8px;font:inherit}input{background:#0d1728;color:white;border:1px solid #50617d}button{margin-top:14px;border:0;background:#7558e8;color:white;font-weight:bold;cursor:pointer}.error{color:#ffb5b5}</style></head><body><div class="card"><h2>🎬 Khmer Drama AI Studio V5.4</h2><p>Private access · Enter your app password</p><form method="post" action="/login"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required autofocus><button type="submit">Sign in</button></form>ERROR_MESSAGE</div></body></html>'''


@app.before_request
def require_authentication():
    # Every app endpoint, including API processing and health status, is private.
    if request.endpoint in ('login', 'static'):
        return None
    if session.get('authenticated') is True:
        return None
    if request.path == '/process' or request.method != 'GET':
        return jsonify(error='Sign in required. Open the app home page first.'), 401
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute; 20 per hour')
def login():
    if request.method == 'POST':
        candidate = request.form.get('password', '')
        if hmac.compare_digest(candidate.encode('utf-8'), _password.encode('utf-8')):
            session.clear()
            session.permanent = True
            session['authenticated'] = True
            response = redirect(url_for('home'))
            response.headers['Cache-Control'] = 'no-store'
            return response
        message = '<p class="error">Incorrect password. Please try again.</p>'
    else:
        if session.get('authenticated'):
            return redirect(url_for('home'))
        message = ''
    response = app.make_response(render_template_string(LOGIN_PAGE.replace('ERROR_MESSAGE', message)))
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.post('/logout')
def logout():
    session.clear()
    response = redirect(url_for('login'))
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(429)
def rate_limited(error):
    return jsonify(error='Too many requests. Please wait before trying again. Successful jobs are limited to 5 per hour; other requests have a separate safety limit.'), 429


@app.get('/')
def home():
    return render_template_string(PAGE)


@app.get('/health')
def health():
    return jsonify(status='ok', version='5.4', translation_model=MODEL, fallback_model=FALLBACK_MODEL or None, tts_engine='gTTS Khmer (free, online)', gemini_key_configured=bool(os.getenv('GEMINI_API_KEY')))


@app.get('/diagnostics/tiktok')
@limiter.limit('10 per hour')
def tiktok_diagnostics():
    """Local-only checks: no TikTok network request and no secret disclosure."""
    result = {'version': '5.4', 'network_tested': False,
              'crawler_binary': 'PRESENT' if os.path.isfile('/usr/local/bin/tiktok_crawler') else 'MISSING',
              'session': 'NOT_CONFIGURED'}
    raw = os.getenv('TIKTOK_COOKIES_B64', '').strip()
    if raw:
        try:
            data = base64.b64decode(raw, validate=True)
            count = tiktok_cookie_check(data)
            result['session'] = 'FORMAT_OK_MSTOKEN_PRESENT'
            result['cookie_rows'] = count
        except (binascii.Error, ValueError, UnicodeError):
            result['session'] = 'INVALID_OR_MSTOKEN_MISSING'
    response = jsonify(result)
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.post('/process')
@limiter.limit('5 per hour', deduct_when=lambda response: response.status_code == 200)
def process():
    try:
        if not os.getenv('GEMINI_API_KEY'):
            return jsonify(error='Missing GEMINI_API_KEY in Render Environment'), 500
        if request.form.get('authorized') != 'yes':
            return jsonify(error='Confirm that you have permission to use this video'), 400
        upload = request.files.get('video')
        url = request.form.get('url', '').strip()
        if bool(upload and upload.filename) == bool(url):
            return jsonify(error='Provide either an MP4 file or one authorized URL'), 400
        language = request.form.get('language', 'auto')
        if language not in LANGUAGES:
            return jsonify(error='Unsupported language selection'), 400
        male = request.form.get('male', 'low')
        female = request.form.get('female', 'high')
        if male not in ('low', 'normal') or female not in ('high', 'normal'):
            return jsonify(error='Invalid voice option'), 400
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            video = folder / 'input.mp4'
            if url:
                if platform_name(url):
                    download_platform_video(url, video)
                else:
                    if not urlparse(url).path.lower().endswith('.mp4'):
                        url = resolve_authorized_page(url)
                    download_mp4(url, video)
            else:
                if not upload.filename.lower().endswith('.mp4'):
                    return jsonify(error='Only MP4 uploads supported'), 400
                upload.save(video)
            length = video_duration(video)
            if not 0 < length <= MAX_SECONDS:
                return jsonify(error='Episode must be between 0 and 90 seconds'), 400
            audio = folder / 'original_audio.mp3'
            run_cmd('ffmpeg', '-y', '-i', str(video), '-vn', '-ac', '1', '-ar', '16000', '-b:a', '48k', str(audio))
            client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
            segments = translate_audio(client, audio, length, language)
            if not segments:
                return jsonify(error='No speech was detected or translated'), 422
            voice = dub_audio(segments, folder, length, male, female)
            result = folder / 'dubbed.mp4'
            # Keep original audio very quiet under the dubbed speech; does not isolate music from speech.
            run_cmd('ffmpeg', '-y', '-i', str(video), '-i', str(voice), '-filter_complex',
                    '[0:a]volume=0.10[background];[background][1:a]amix=inputs=2:duration=first:dropout_transition=0[mix]',
                    '-map', '0:v:0', '-map', '[mix]', '-c:v', 'copy', '-c:a', 'aac', '-t', str(length), str(result))
            srt = folder / 'khmer_subtitles.srt'
            srt.write_text('\n'.join(f"{i}\n{timestamp(s['start'])} --> {timestamp(s['end'])}\n{s['khmer']}\n" for i, s in enumerate(segments, 1)), encoding='utf-8')
            transcript = folder / 'transcript.json'
            transcript.write_text(json.dumps({'source_language': language, 'segments': segments}, ensure_ascii=False, indent=2), encoding='utf-8')
            archive = folder / 'khmer_dubbed.zip'
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
                for name, path in [('dubbed.mp4', result), ('khmer_subtitles.srt', srt), ('transcript.json', transcript)]:
                    output.write(path, name)
            return send_file(archive, as_attachment=True, download_name='khmer_dubbed_episode.zip', mimetype='application/zip')
    except (ValueError, RuntimeError, subprocess.TimeoutExpired, requests.RequestException) as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        app.logger.exception('Processing failed')
        return jsonify(error=f'Processing failed ({type(exc).__name__}). Check Render logs.'), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '10000')))
