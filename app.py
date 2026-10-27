import ipaddress
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, render_template_string, request, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from google import genai
from google.genai import types
from gtts import gTTS
from pydub import AudioSegment

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 45 * 1024 * 1024
limiter = Limiter(get_remote_address, app=app, default_limits=['20 per hour'], storage_uri='memory://')
MAX_SECONDS = 90
MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024
MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.8-flash')
LANGUAGES = {'auto': 'Automatically identify the spoken language', 'en': 'English', 'zh': 'Mandarin Chinese', 'ko': 'Korean', 'ja': 'Japanese', 'th': 'Thai', 'vi': 'Vietnamese', 'fr': 'French', 'es': 'Spanish'}

PAGE = '''<!doctype html><html lang="km"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Khmer Drama AI Studio V4.1</title><style>body{margin:0;padding:20px;background:#0b1220;color:#eaf0ff;font:15px Arial,sans-serif}main{max-width:850px;margin:auto}section{background:#1c273a;padding:22px;margin:16px 0;border-radius:16px}h1{font-size:28px}label{display:block;margin:14px 0 6px}input,select,textarea,button{font:inherit;padding:11px;border-radius:8px;box-sizing:border-box}input[type=url],input[type=text],select,textarea{width:100%;background:#0d1728;color:#fff;border:1px solid #50617d}input[type=number]{width:100px;background:#0d1728;color:#fff;border:1px solid #50617d}button{background:#7558e8;color:white;border:0;cursor:pointer;font-weight:bold}button:disabled{opacity:.5}.hint{color:#a9b9d3;font-size:13px;line-height:1.5}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.error{color:#ffb5b5}a{color:#b7c8ff}#status{white-space:pre-wrap;line-height:1.5}</style></head><body><main><h1>🎬 Khmer Drama AI Studio V4.1</h1><p>Multi-language → Khmer · Free Edition · Authorized downloads only</p><section><h2>1. Video source</h2><label>Upload MP4 episodes (up to 5 files)</label><input id="files" type="file" accept="video/mp4" multiple><p class="hint">Name files 001.mp4, 002.mp4, etc. Upload OR URL; do not use both.</p><label>OR direct public HTTPS MP4 URL</label><input id="url" type="url" placeholder="https://your-authorized-host.com/episode.mp4"><p class="hint">A video player page (such as Hongguo /player/...) is not a direct MP4. URLs require an operator-configured host allowlist. No VIP, DRM or login bypass.</p><div class="grid"><div><label>From episode</label><input id="start" type="number" min="1" value="1"></div><div><label>To episode</label><input id="end" type="number" min="1" value="1"></div></div><p class="hint">For uploads, episode numbers correspond to sorted filenames. URL mode accepts one MP4 episode only.</p></section><section><h2>2. Translation & voices</h2><label>Original spoken language</label><select id="language"><option value="auto">Auto detect</option><option value="en">English</option><option value="zh">Chinese / Mandarin</option><option value="ko">Korean</option><option value="ja">Japanese</option><option value="th">Thai</option><option value="vi">Vietnamese</option><option value="fr">French</option><option value="es">Spanish</option></select><label>Target language</label><input type="text" value="Khmer (ភាសាខ្មែរ)" readonly><div class="grid"><div><label>Male voice (estimated)</label><select id="male"><option value="low">Lower pitch</option><option value="normal">Normal pitch</option></select></div><div><label>Female voice (estimated)</label><select id="female"><option value="high">Higher pitch</option><option value="normal">Normal pitch</option></select></div></div><p class="hint">Speaker and gender classification are estimates. Free Khmer gTTS voice with pitch adjustments. No Gemini TTS quota used. Gender estimation can be wrong; no voice cloning, emotion control, or visual lip-sync.</p></section><section><h2>3. Translate, dub & export</h2><button id="go" onclick="run()">Download (if URL) + Translate + Khmer Dub</button><p id="status" role="status"></p><div id="results"></div><p class="hint">Each episode: maximum 90 seconds. Processing may fail on free hosting due to quotas, timeout or memory.</p></section></main><script>
async function run(){const files=[...document.getElementById('files').files].sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}));const url=document.getElementById('url').value.trim();const start=Number(document.getElementById('start').value),end=Number(document.getElementById('end').value);const status=document.getElementById('status'),out=document.getElementById('results'),btn=document.getElementById('go');out.replaceChildren();if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end<start||end-start+1>5){status.textContent='Select 1–5 episodes in a valid range.';return}if((files.length>0)===(url.length>0)){status.textContent='Provide MP4 uploads OR one direct MP4 URL.';return}if(files.length&&files.length<end){status.textContent='Not enough uploaded episodes for selected range.';return}if(url&&(start!==1||end!==1)){status.textContent='Direct URL supports one episode only (1 to 1).';return}btn.disabled=true;try{for(let i=start;i<=end;i++){status.textContent='Processing episode '+i+'... This can take several minutes.';const fd=new FormData();if(files.length)fd.append('video',files[i-1]);else fd.append('url',url);fd.append('language',document.getElementById('language').value);fd.append('male',document.getElementById('male').value);fd.append('female',document.getElementById('female').value);const response=await fetch('/process',{method:'POST',body:fd});if(!response.ok){let err=await response.text();try{err=JSON.parse(err).error||err}catch{}throw Error('Episode '+i+': '+err)}const blob=await response.blob(),href=URL.createObjectURL(blob),a=document.createElement('a');a.href=href;a.download='khmer_episode_'+String(i).padStart(3,'0')+'.zip';a.textContent='⬇ Download episode '+i+' (MP4 + SRT + JSON)';a.style.display='block';a.style.margin='10px 0';out.append(a)}status.textContent='Finished. Use the download links below.'}catch(e){status.textContent='Error: '+e.message;status.className='error'}finally{btn.disabled=false}}
</script></body></html>'''


def run_cmd(*args, timeout=150):
    p = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('Media processing error: ' + p.stderr[-350:])
    return p.stdout


def video_duration(path):
    return float(run_cmd('ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path), timeout=20).strip())


def allowed_url(url):
    p = urlparse(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Only public HTTPS URLs on port 443 are supported')
    if not p.path.lower().endswith('.mp4'):
        raise ValueError('Use a direct .mp4 URL, not a video player or drama page')
    hosts = [x.strip().lower() for x in os.getenv('ALLOWED_VIDEO_HOSTS', '').split(',') if x.strip()]
    if p.hostname.lower() not in hosts:
        raise ValueError('Video host is not authorized. Add its exact hostname to ALLOWED_VIDEO_HOSTS in Render.')
    ips = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not ips or any(not ipaddress.ip_address(x[4][0]).is_global for x in ips):
        raise ValueError('Private or reserved IP addresses are blocked')
    return p


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
        response = client.models.generate_content(model=MODEL, contents=[upload, prompt], config=types.GenerateContentConfig(response_mime_type='application/json'))
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


@app.get('/')
def home():
    return render_template_string(PAGE)


@app.get('/health')
def health():
    return jsonify(status='ok', version='4.1', translation_model=MODEL, tts_engine='gTTS Khmer (free, online)', gemini_key_configured=bool(os.getenv('GEMINI_API_KEY')))


@app.post('/process')
@limiter.limit('5 per hour')
def process():
    try:
        if not os.getenv('GEMINI_API_KEY'):
            return jsonify(error='Missing GEMINI_API_KEY in Render Environment'), 500
        upload = request.files.get('video')
        url = request.form.get('url', '').strip()
        if bool(upload and upload.filename) == bool(url):
            return jsonify(error='Provide either an MP4 file or a direct MP4 URL'), 400
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
