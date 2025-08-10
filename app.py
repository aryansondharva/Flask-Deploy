import os
import shutil
from io import BytesIO
import requests
from dotenv import load_dotenv

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import assemblyai as aai

# Load environment variables
load_dotenv()
MURF_API_KEY = os.getenv("MURF_API_KEY")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print("✅ Loaded Murf API Key:", bool(MURF_API_KEY))
print("✅ Loaded AssemblyAI Key:", bool(ASSEMBLYAI_API_KEY))
print("✅ Loaded Gemini API Key:", bool(GEMINI_API_KEY))

# Initialize AssemblyAI
aai.settings.api_key = ASSEMBLYAI_API_KEY
transcriber = aai.Transcriber()

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files from the 'static' directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Root route serving index.html
@app.get("/")
async def root():
    return FileResponse("static/index.html")


# Text to Speech generation request model
class TextRequest(BaseModel):
    text: str
    voice: str = "default"


# Voice ID map for Murf API
VOICE_MAP = {
    "default": "en-US-natalie",
    "narrator": "en-US-terrell",
    "support": "en-US-miles",
    "sergeant": "en-US-ken",
    "game": "en-US-paul"
}


# Generate TTS using Murf API
@app.post("/generate")
async def generate_voice(data: TextRequest):
    voice_id = VOICE_MAP.get(data.voice.lower(), "en-US-natalie")

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": MURF_API_KEY
    }
    payload = {"text": data.text, "voice_id": voice_id}

    response = requests.post("https://api.murf.ai/v1/speech/generate", headers=headers, json=payload)
    if response.status_code == 200:
        result = response.json()
        return JSONResponse(content={"audio_url": result.get("audioFile")})
    else:
        return JSONResponse(status_code=response.status_code, content={"error": response.text})


# Directory to save uploaded files
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    file_location = f"{UPLOAD_DIR}/{file.filename}"
    with open(file_location, "wb") as f:
        shutil.copyfileobj(file.file, f)
    file_stat = os.stat(file_location)
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": file_stat.st_size,
        "message": "🎤 Recording uploaded successfully!",
        "icon": "🎤"
    }


@app.post("/transcribe/file")
async def transcribe_audio(file: UploadFile = File(...)):
    try:
        audio_bytes = await file.read()
        transcript = transcriber.transcribe(audio_bytes)
        return {
            "transcription": transcript.text,
            "status": "🔊 Transcription complete!",
            "icon": "🔊"
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# Serve logos
@app.get("/logo/start")
async def get_start_logo():
    return FileResponse("static/logos/start_recording.png")


@app.get("/logo/microphone")
async def get_microphone_logo():
    return FileResponse("static/logos/microphone.png")


# Transcribe audio → Generate Murf AI voice reply (direct streaming)
@app.post("/voice-reply")
async def voice_reply(file: UploadFile = File(...), voice: str = Form("default")):
    try:
        audio_bytes = await file.read()
        transcript = transcriber.transcribe(audio_bytes)
        text = transcript.text

        voice_id = VOICE_MAP.get(voice.lower(), "en-US-natalie")
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": MURF_API_KEY
        }
        payload = {"text": text, "voice_id": voice_id, "format": "mp3"}
        murf_response = requests.post("https://api.murf.ai/v1/speech/generate", headers=headers, json=payload)

        if murf_response.status_code != 200:
            return JSONResponse(status_code=murf_response.status_code, content={"error": murf_response.text})

        audio_url = murf_response.json().get("audioFile")
        if not audio_url:
            return JSONResponse(status_code=500, content={"error": "No audio file URL returned by Murf AI"})

        audio_file = requests.get(audio_url)
        if audio_file.status_code != 200:
            return JSONResponse(status_code=500, content={"error": "Failed to download audio from Murf AI"})

        return StreamingResponse(BytesIO(audio_file.content), media_type="audio/mpeg")

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/murf-tts")
async def murf_tts_alias(file: UploadFile = File(...), voice: str = Form("default")):
    return await voice_reply(file, voice)


# JSON Text → TTS Request model
class TTSRequest(BaseModel):
    text: str
    voice: str = "default"


@app.post("/murf-tts-json")
async def murf_tts_json(data: TTSRequest):
    try:
        voice_id = VOICE_MAP.get(data.voice.lower(), "en-US-natalie")
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": MURF_API_KEY
        }
        payload = {"text": data.text, "voice_id": voice_id, "format": "mp3"}

        murf_response = requests.post("https://api.murf.ai/v1/speech/generate", headers=headers, json=payload)
        if murf_response.status_code != 200:
            return JSONResponse(status_code=murf_response.status_code, content={"error": murf_response.text})

        audio_url = murf_response.json().get("audioFile")
        if not audio_url:
            return JSONResponse(status_code=500, content={"error": "No audio file URL returned by Murf AI"})

        audio_file = requests.get(audio_url)
        if audio_file.status_code != 200:
            return JSONResponse(status_code=500, content={"error": "Failed to download audio from Murf AI"})

        return StreamingResponse(BytesIO(audio_file.content), media_type="audio/mpeg")

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# Gemini LLM query
class LLMRequest(BaseModel):
    text: str


@app.post("/llm/query")
async def llm_query(request: LLMRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    gemini_url = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": request.text}]}]}

    try:
        response = requests.post(gemini_url, headers=headers, params=params, json=payload)
        response.raise_for_status()
        data = response.json()

        if "candidates" in data and len(data["candidates"]) > 0:
            return {"response": data["candidates"][0]["content"]["parts"][0]["text"]}
        else:
            raise HTTPException(status_code=500, detail="No response from Gemini API")

    except requests.HTTPError:
        raise HTTPException(status_code=response.status_code, detail=f"Gemini API error: {response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
