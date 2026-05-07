import os
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from faster_whisper import WhisperModel
from pydantic import BaseModel
import asyncio
from concurrent.futures import ThreadPoolExecutor

from psychotherapy_agents import run_psychotherapy_pipeline

app = FastAPI(title="Lumen Psychotherapy Transcriber & Agent Pipeline")

# Allow local frontend to communicate with this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Faster-Whisper. "base" provides good speed and accuracy for laptops.
# `device="cpu"` ensures it runs locally without needing a GPU.
# `compute_type="int8"` significantly reduces memory usage on CPUs.
print("Loading Whisper Model (base)... this may take a moment on first run as it downloads the model.")
model = WhisperModel("base", device="cpu", compute_type="int8")
print("Whisper Model loaded successfully.")

# Thread pool for blocking operations like transcribing or running the agent graph
executor = ThreadPoolExecutor(max_workers=4)

def transcribe_audio_blocking(file_path: str) -> str:
    """Run transcription in a separate thread so it doesn't block FastAPI."""
    segments, info = model.transcribe(file_path, beam_size=5)
    transcript = " ".join([segment.text for segment in segments])
    return transcript

@app.get("/")
def serve_frontend():
    """Serves the frontend UI."""
    return FileResponse("frontend/recorder.html")

@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """Receives audio file from frontend and transcribes it locally."""
    tmp_path = None
    try:
        # Save uploaded file temporarily to disk
        suffix = os.path.splitext(audio.filename)[1] if audio.filename else ".webm"
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, 'wb') as f:
            content = await audio.read()
            f.write(content)
        
        # Run transcription in a background thread
        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(executor, transcribe_audio_blocking, tmp_path)
        
        return {"transcript": transcript.strip()}
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
        
    finally:
        # Cleanup temp file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

class SummaryRequest(BaseModel):
    transcript: str

def run_pipeline_blocking(transcript: str) -> str:
    """Run the LangGraph multi-agent pipeline in a separate thread."""
    return run_psychotherapy_pipeline(transcript)

@app.post("/api/summarize")
async def summarize_transcript(req: SummaryRequest):
    """Takes raw transcript and runs the multi-agent clinical note pipeline."""
    try:
        loop = asyncio.get_event_loop()
        final_note = await loop.run_in_executor(executor, run_pipeline_blocking, req.transcript)
        return {"final_note": final_note}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    # Run standalone server on 8003 to not conflict with the main lumen app on 8000
    uvicorn.run(app, host="127.0.0.1", port=8003)
