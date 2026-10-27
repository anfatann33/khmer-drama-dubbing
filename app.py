
import os
import json
import time
import wave
import tempfile
import subprocess
from pathlib import Path

from flask import Flask, request, jsonify, send_file
from google import genai
from google.genai import types

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="km">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Khmer Drama AI Dubbing</title>
<style>
body {
  background: #101728;
  color: white;
  font-family: Arial, sans-serif;
  padding: 30px;
}
main {
  max-width: 650px;
  margin: auto;
  background: #1d2940;
  padding: 30px;
  border-radius: 20px;
}
input, button {
  display: block;
  width: 100%;
  padding: 14px;
  margin: 16px 0;
  box-sizing: border-box;
}
button {
  background: #765bff;
  color: white;
  border: none;
  border-radius: 10px;
  cursor: pointer;
}
video { width: 100%; }
a { color: #a9dcff; }
</style>
</head>
<body>
<main>
<h1>🎬 Khmer Drama AI Dubbing</h1>
<p>Upload MP4 → Translate → Khmer Voice → Export</p>
<input id="video" type="file" accept="video/mp4">
<button onclick="start()">Start AI Dubbing</button>
<p id="status"></p>
<div id="result"></div>
</main>
<script>
async function start() {
  const file = document.getElementById("video").files[0];
  if (!file) return alert("Please select an MP4 video");

  const form = new FormData();
  form.append("video", file);

  document.getElementById("status").textContent =
    "Processing video. Please wait...";

  try {
    const response = await fetch("/process", {
      method: "POST",
      body: form
    });

    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);

    document.getElementById("status").textContent =
      "Dubbing completed!";

    document.getElementById("result").innerHTML =
      '<video controls src="' + url + '"></video>' +
      '<p><a href="' + url +
      '" download="khmer_dubbed.mp4">Download MP4</a></p>';

  } catch (error) {
    document.getElementById("status").textContent =
      "Error: " + error.message;
  }
}
</script>
</body>
</html>
"""

def run(command):
    subprocess.run(command, check=True, capture_output=True)

@app.route("/")
def home():
    return HTML

@app.route("/process", methods=["POST"])
def process():
    try:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            return jsonify(error="Gemini API key missing"), 500

        uploaded = request.files.get("video")
        if not uploaded or not uploaded.filename.lower().endswith(".mp4"):
            return jsonify(error="Upload an MP4 file"), 400

        client = genai.Client(api_key=key)

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            video = folder / "input.mp4"
            audio = folder / "audio.mp3"
            output = folder / "output.mp4"
            voice = folder / "voice.wav"

            uploaded.save(video)

            run([
                "ffmpeg", "-y", "-i", str(video),
                "-vn", "-ac", "1",
                "-ar", "16000", str(audio)
            ])

            remote = client.files.upload(file=str(audio))

            for _ in range(60):
                remote = client.files.get(name=remote.name)
                if remote.state and remote.state.name == "ACTIVE":
                    break
                if remote.state and remote.state.name == "FAILED":
                    raise RuntimeError("Audio processing failed")
                time.sleep(2)
            else:
                raise RuntimeError("Audio processing timed out")

            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=[
                    remote,
                    """Transcribe the spoken dialogue in this audio.
                    Translate all dialogue naturally into Khmer.
                    Preserve the meaning and emotional tone.
                    Return only the Khmer spoken dialogue.
                    Do not add explanations."""
                ]
            )

            khmer_text = response.text

            speech = client.models.generate_content(
                model="gemini-3.8-flash-tts",
                contents=(
                    "Speak this text naturally in Khmer: "
                    + khmer_text
                ),
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=
                            types.PrebuiltVoiceConfig(
                                voice_name="Kore"
                            )
                        )
                    )
                )
            )

            audio_data = None
            for part in speech.candidates[0].content.parts:
                if part.inline_data:
                    audio_data = part.inline_data.data
                    break

            if not audio_data:
                raise RuntimeError("TTS returned no audio")

            with wave.open(str(voice), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(audio_data)

            run([
                "ffmpeg", "-y",
                "-i", str(video),
                "-i", str(voice),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest", str(output)
            ])

            return send_file(
                output,
                mimetype="video/mp4",
                as_attachment=True,
                download_name="khmer_dubbed.mp4"
            )

    except Exception as e:
        return jsonify(error=str(e)), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
