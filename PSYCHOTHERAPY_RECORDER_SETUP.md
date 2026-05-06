# Psychotherapy Recorder Setup Guide

## Overview
This feature provides local-only psychotherapy session transcription with AI-generated SOAP notes using:
- **faster-whisper** for local audio transcription
- **Ollama** with **tinyllama:1.1b** for local LLM summarization
- **FastAPI** server for the backend API
- **Browser-based** frontend for recording and file upload

All processing happens locally - no data leaves your computer.

## Prerequisites

### 1. Install Ollama
```bash
# On macOS
brew install ollama

# Or download from https://ollama.com
```

### 2. Pull the LLM Model
```bash
ollama pull tinyllama:1.1b
```

### 3. Install Python 3.13+ (if not already installed)
```bash
brew install python@3.13
```

## Setup Instructions

### Step 1: Navigate to Project
```bash
cd /path/to/Lumen
git checkout henrik1  # or your feature branch
```

### Step 2: Create Virtual Environment
```bash
python3.13 -m venv .venv
```

### Step 3: Activate Virtual Environment
```bash
source .venv/bin/activate
```

### Step 4: Install Dependencies
```bash
pip install faster-whisper langgraph langchain langchain-ollama httpx fastapi uvicorn python-multipart
```

This installs:
- `faster-whisper` - Local speech-to-text
- `langchain` & `langgraph` - Multi-agent pipeline
- `ollama` - Local LLM integration
- `fastapi` & `uvicorn` - Backend server

## Running the Application

### Step 1: Start Ollama (in a separate terminal)
```bash
ollama serve
```
Wait for: `level=INFO msg="Listening on 127.0.0.1:11434"`

**Optional:** Enable GPU acceleration for faster responses:
```bash
OLLAMA_NUM_GPU=99 ollama serve
```

### Step 2: Start the Transcription Server (in another terminal)
```bash
cd /path/to/Lumen
source .venv/bin/activate
python3 transcribe_server.py
```

Wait for: `INFO: Uvicorn running on http://127.0.0.1:8003`

**Note:** First run will download the "base" whisper model (~140MB) - this may take a few minutes.

**Performance:** On Apple M2 8GB with tinyllama:1.1b + GPU:
- Transcription: ~11 seconds for 2-minute session
- SOAP note generation: 30-60 seconds

### Step 3: Open the Recorder in Browser
Open this URL in Chrome/Safari/Firefox:
```
http://127.0.0.1:8003/
```

## Using the Recorder

### Option 1: Live Recording
1. Click **"Start Recording"** - grant microphone permission
2. Use **Pause/Resume** buttons as needed
3. Click **"Stop & Transcribe"** when done
4. Wait for transcription to complete (progress bar shows status)
5. Click **"Generate Agentic Clinical Note (SOAP)"** for AI summary

### Option 2: Upload MP3 File
1. Click **"Upload MP3"** button
2. Select an MP3 file from your computer
3. Transcription starts automatically
4. Click **"Generate Agentic Clinical Note (SOAP)"** for AI summary

## Troubleshooting

### "Connection refused" Error
- Ensure Ollama is running: `curl http://localhost:11434/api/tags`
- Check server is running: `curl http://127.0.0.1:8003/`

### Slow Transcription/Summarization
- Verify Ollama uses GPU: Check server logs for `"compute": "gpu"` 
- Use smaller model: `ollama pull tinyllama:1.1b` (default)
- Larger model option: `ollama pull phi3:latest` (slower but more accurate)

### Microphone Not Working
- Check browser permissions (lock icon in address bar)
- Try Chrome/Safari if Firefox has issues

### Server Crashes
- Check logs: `tail -50 /tmp/transcribe_server.log`
- Restart: `python3 transcribe_server.py`

## Project Structure
```
Lumen/
├── transcribe_server.py      # FastAPI backend server
├── psychotherapy_agents.py    # LangGraph multi-agent pipeline
├── frontend/
│   └── recorder.html        # Browser-based UI
└── .venv/                    # Python virtual environment (not committed)
```

## Configuration

### Change LLM Model
Edit `psychotherapy_agents.py` line 17:
```python
model_name = os.getenv("LUMEN_MEDIUM_MODEL", "tinyllama:1.1b")
# Change "tinyllama:1.1b" to "phi3:latest" or other Ollama model
```

### Change Server Port
Edit `transcribe_server.py` last line:
```python
uvicorn.run(app, host="127.0.0.1", port=8003)  # Change 8003 to desired port
```

## Notes for Developers
- **Isolation:** This feature is designed to be isolated from the main Lumen app (port 8000) 
- **Future Integration:** Will connect to `SessionNote` model in main app
- **Local Only:** No data sent to external APIs - all processing on your machine
- **GPU Recommended:** Apple M1/M2/M3 Macs work best with `OLLAMA_NUM_GPU=99`

## Testing with Sample Session

Generate a sample psychotherapy session MP3 for testing:

```bash
python3 generate_sample_session.py
```

This creates `sample_psychotherapy_session.mp3` on your Desktop (~2 minutes of audio). Upload it to the recorder to test the full flow.

**What's in the sample:** A realistic therapy session discussing work stress, anxiety, sleep issues, and coping strategies.

## Support
For issues, check:
- Server logs: `/tmp/transcribe_server.log`
- Ollama logs: `tail -f ~/.ollama/logs/server.log`
