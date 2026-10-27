import os, re, json, math, time, socket, ipaddress, tempfile, subprocess
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from flask import Flask, request, jsonify, send_file, render_template_string
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from google import genai
from google.genai import types
from gtts import gTTS
from pydub import AudioSegment

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 45 * 1024 * 1024
limiter = Limiter(get_remote_address, app=app, default_limits=['15 per hour'], storage_uri='memory://')
MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.8-flash')
MAX_SECONDS = 90
MAX_EPISODES = 5

PAGE = '''<!doctype html><html lang="km"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Khmer Drama V3</title><style>body{background:#111827;color:#f9fafb;font:16px Arial,sans-serif;margin:0;padding:24px}main{max-width:850px;margin:auto}section{background:#1f2937;border-radius:16px;padding:22px;margin:18px 0}input,select,button{padding:12px;border-radius:9px;border:1px solid #475569;box-sizing:border-box}input[type=text],input[type=url]{width:100%;background:#0f172a;color:white}button{background:#7155f5;color:white;border:0;cursor:pointer}button:disabled{opacity:.5}label{display:block;margin:10px 0}.small{color:#a9b4c6;font-size:14px}#status{white-space:pre-wrap}a{color:#a5b4fc}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}video{max-width:100%}</style></head><body><main><h1>🎬 Khmer Drama AI Studio V3</h1><p>Free edition · Authorized videos only</p><section><h2>1. Import episodes</h2><label>Upload MP4 episodes (maximum 5)</label><input id="files" type="file" accept="video/mp4" multiple><p class="small">Episode order follows filename sorting. Name files 001.mp4, 002.mp4...</p><label>OR direct MP4 HTTPS URL (one episode)</label><input id="url" type="url" placeholder="https://example.com/episode.mp4"><p class="small">Only publicly downloadable direct MP4 URLs; not drama detail pages, VIP or DRM.</p><div class="grid"><label>From episode <input id="from" type="number" min="1" value="1" style="width:90px"></label><label>To episode <input id="to" type="number" min="1" value="1" style="width:90px"></label></div></section><section><h2>2. Voice options</h2><label>Male voice <select id="male"><option value="low">Lower pitch</option><option value="normal">Normal</option></select></label><label>Female voice <select id="female"><option value="high">Higher pitch</option><option value="normal">Normal</option></select></label><label><input id="sub" type="checkbox" checked> Generate Khmer SRT subtitles</label><p class="small">Speaker/gender detection is an estimate. Voices are pitch variations of a Khmer TTS voice, not authentic male/female actors. Lip movement is NOT edited.</p></section><section><h2>3. Process & export</h2><button id="go" onclick="go()">Translate + Dub selected episodes</button><p id="status"></p><div id="out"></div></section></main><script>
async function go(){const files=[...document.getElementById('files').files].sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}));const url=document.getElementById('url').value.trim();const start=Number(document.getElementById('from').value),end=Number(document.getElementById('to').value);const status=document.getElementById('status'),out=document.getElementById('out'),btn=document.getElementById('go');out.innerHTML='';if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end<start||end-start+1>5){status.textContent='Select 1 to 5 episodes in a valid range.';return}if(!files.length&&!url){status.textContent='Choose MP4 files or paste a direct MP4 URL.';return}if(files.length&&url){status.textContent='Use uploads OR URL, not both.';return}if(url&&(start!==1||end!==1)){status.textContent='Direct URL mode supports one episode only (1–1).';return}if(files.length<end){status.textContent='Upload at least '+end+' numbered episodes.';return}btn.disabled=true;try{for(let i=start;i<=end;i++){status.textContent='Processing episode '+i+' of '+end+'... (may take several minutes)';const form=new FormData();if(files.length)form.append('video',files[i-1]);else form.append('url',url);form.append('male',document.getElementById('male').value);form.append('female',document.getElementById('female').value);const r=await fetch('/process',{method:'POST',body:form});if(!r.ok){let msg=await r.text();try{msg=JSON.parse(msg).error||msg}catch{}throw new Error('Episode '+i+': '+msg)}const blob=await r.blob(),link=URL.createObjectURL(blob);const a=document.createElement('a');a.href=link;a.download='episode_'+String(i).padStart(3,'0')+'.zip';a.textContent='Download episode '+i+' (MP4 + SRT + transcript)';out.append(a,document.createElement('br'));}status.textContent='Done. Download each episode ZIP.'}catch(e){status.textContent='Error: '+e.message}finally{btn.disabled=false}}
</script></body></html>'''

def cmd(*args):
    p=subprocess.run(list(args),capture_output=True,text=True,timeout=120)
    if p.returncode: raise RuntimeError('FFmpeg error: '+p.stderr[-500:])

def duration(path):
    p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],capture_output=True,text=True,timeout=15,check=True)
    return float(p.stdout.strip())

def safe_download(url, dest):
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Only direct HTTPS MP4 URLs are accepted')
    if not parsed.path.lower().endswith('.mp4'):
        raise ValueError('This is not a direct .mp4 URL. Detail/episode pages are not supported.')
    # Restrict hostnames to an operator-controlled allowlist to prevent SSRF.
    allowed=[s.strip().lower() for s in os.getenv('ALLOWED_VIDEO_HOSTS','').split(',') if s.strip()]
    if parsed.hostname.lower() not in allowed:
        raise ValueError('URL host is not allowlisted. Set ALLOWED_VIDEO_HOSTS for an authorized media host.')
    addresses=socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
        raise ValueError('Non-public address blocked')
    req=Request(url,headers={'User-Agent':'KhmerDramaV3/1.0'})
    with urlopen(req,timeout=15) as response:
        if response.geturl()!=url: raise ValueError('Redirects are not allowed')
        ct=response.headers.get('Content-Type','').lower()
        if 'video/mp4' not in ct and 'application/octet-stream' not in ct:
            raise ValueError('URL did not return MP4 content')
        with open(dest,'wb') as f:
            size=0
            while True:
                chunk=response.read(65536)
                if not chunk: break
                size+=len(chunk)
                if size>40*1024*1024: raise ValueError('Video exceeds 40MB limit')
                f.write(chunk)

def translate(client,audio,video_seconds):
    uploaded=client.files.upload(file=str(audio))
    for _ in range(60):
        uploaded=client.files.get(name=uploaded.name)
        state=getattr(getattr(uploaded,'state',None),'name','')
        if state=='ACTIVE': break
        if state=='FAILED': raise RuntimeError('Gemini audio upload failed')
        time.sleep(2)
    else: raise RuntimeError('Gemini file processing timed out')
    prompt='''Analyze Mandarin/Chinese speech in this audio and translate into natural spoken Khmer. Identify different speakers as speaker_1, speaker_2 etc. Guess voice type male/female/unknown from audio (do not claim certainty). Give start/end in seconds relative to audio. Output ONLY JSON array of objects with keys start,end,speaker,gender,khmer. Each segment should be one short utterance. No markdown. Time range must be accurate and within the audio duration.'''
    response=client.models.generate_content(model=MODEL,contents=[uploaded,prompt],config=types.GenerateContentConfig(response_mime_type='application/json'))
    try: segments=json.loads(response.text)
    except Exception: raise RuntimeError('Gemini returned invalid JSON')
    if isinstance(segments,dict): segments=segments.get('segments',[])
    if not isinstance(segments,list): raise RuntimeError('Unexpected transcript format')
    clean=[]
    for s in segments[:100]:
        try:
            start=max(0,float(s['start']));end=min(video_seconds,float(s['end']));khmer=str(s['khmer']).strip()
            if end<=start or not khmer: continue
            clean.append(dict(start=start,end=end,speaker=str(s.get('speaker','unknown')),gender=str(s.get('gender','unknown')).lower(),khmer=khmer))
        except (ValueError,TypeError,KeyError): continue
    return sorted(clean,key=lambda s:s['start'])

def srt_time(t):
    ms=int(max(0,t)*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'

def make_audio(segments, folder, length, male, female):
    canvas=AudioSegment.silent(duration=int(length*1000)+300,frame_rate=24000)
    for i,s in enumerate(segments):
        mp3=folder/f'speech_{i}.mp3'
        try: gTTS(text=s['khmer'],lang='km').save(str(mp3))
        except Exception as e: raise RuntimeError('Khmer TTS unavailable: '+str(e))
        part=AudioSegment.from_file(mp3).set_channels(1).set_frame_rate(24000)
        # Pitch change: simple and imperfect; no claim of true male/female voices.
        factor=1.0
        if s['gender']=='male' and male=='low':factor=0.86
        if s['gender']=='female' and female=='high':factor=1.14
        if factor!=1.0:
            part=part._spawn(part.raw_data,overrides={'frame_rate':int(part.frame_rate*factor)}).set_frame_rate(24000)
        target=int((s['end']-s['start'])*1000)
        if len(part)>target and target>=150:
            # speed-up with ffmpeg atempo, preserving pitch of adjusted voice
            temp=folder/f'pitch_{i}.wav'; sped=folder/f'sped_{i}.wav'
            part.export(temp,format='wav')
            speed=min(2.0,len(part)/target)
            cmd('ffmpeg','-y','-i',str(temp),'-filter:a',f'atempo={speed:.4f}',str(sped))
            part=AudioSegment.from_file(sped)
        part=part[:max(1,target)]
        canvas=canvas.overlay(part,position=int(s['start']*1000))
    wav=folder/'dub.wav';canvas.export(wav,format='wav');return wav

@app.get('/')
def home(): return render_template_string(PAGE)

@app.post('/process')
@limiter.limit('5 per hour')
def process():
    try:
        if not os.getenv('GEMINI_API_KEY'): return jsonify(error='Missing GEMINI_API_KEY'),500
        video_file=request.files.get('video');url=request.form.get('url','').strip()
        if bool(video_file) == bool(url): return jsonify(error='Provide either MP4 upload or URL'),400
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);video=folder/'input.mp4'
            if video_file:
                if not video_file.filename.lower().endswith('.mp4'): return jsonify(error='Only MP4 files supported'),400
                video_file.save(video)
            else: safe_download(url,video)
            seconds=duration(video)
            if not 0<seconds<=MAX_SECONDS: return jsonify(error='Maximum video duration is 90 seconds per episode'),400
            audio=folder/'audio.mp3'
            cmd('ffmpeg','-y','-i',str(video),'-vn','-ac','1','-ar','16000','-b:a','48k',str(audio))
            client=genai.Client(api_key=os.environ['GEMINI_API_KEY'])
            segments=translate(client,audio,seconds)
            if not segments: return jsonify(error='No usable dialogue found'),422
            wav=make_audio(segments,folder,seconds,request.form.get('male','low'),request.form.get('female','high'))
            output=folder/'dubbed.mp4'
            # Preserve quiet original soundtrack beneath dubbed dialogue.
            cmd('ffmpeg','-y','-i',str(video),'-i',str(wav),'-filter_complex','[0:a]volume=0.12[bg];[bg][1:a]amix=inputs=2:duration=first:dropout_transition=0[mix]','-map','0:v:0','-map','[mix]','-c:v','copy','-c:a','aac','-t',str(seconds),str(output))
            srt=folder/'subtitles.srt';srt.write_text('\n'.join(f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{s['khmer']}\n" for i,s in enumerate(segments,1)),encoding='utf-8')
            (folder/'transcript.json').write_text(json.dumps(segments,ensure_ascii=False,indent=2),encoding='utf-8')
            import zipfile
            archive=folder/'episode.zip'
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for name,path in [('dubbed.mp4',output),('subtitles.srt',srt),('transcript.json',folder/'transcript.json')]:z.write(path,name)
            return send_file(archive,as_attachment=True,download_name='khmer_dubbed_episode.zip',mimetype='application/zip')
    except (ValueError,RuntimeError) as e: return jsonify(error=str(e)),400
    except Exception as e:
        app.logger.exception('Processing failed')
        return jsonify(error=f'Processing failed ({type(e).__name__}). Check Render logs.'),500

if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','10000')))
