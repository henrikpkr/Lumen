# Psychology Suite (separate module)

This folder contains a standalone FastAPI + HTML workflow for psychotherapy session recording, transcription, and SOAP summarization. It is intentionally separate from the existing Lumen app.

## Setup

Create `.env` in `psychology_suite/`:

```
PSYCH_SUITE_DATABASE_URL=postgresql://user:password@localhost:5432/psychology_suite
PSYCH_SUITE_AUDIO_KEY=base64:REPLACE_WITH_BASE64_KEY
PSYCH_SUITE_BOOTSTRAP_EMAIL=clinician@clinic.local
PSYCH_SUITE_BOOTSTRAP_PASSWORD=change-me
PSYCH_SUITE_BOOTSTRAP_NAME=Clinic Psychologist
```

Generate a key (example):

```
python - <<'PY'
import base64, os
print("base64:" + base64.b64encode(os.urandom(32)).decode())
PY
```

Install deps:

```
pip install -r requirements.txt
```

Run the app:

```
uvicorn psychology_suite.psychology_suite.app:app --reload --host 127.0.0.1 --port 8010
```

Open `http://127.0.0.1:8010/login`.

## Externally managed environments

If you cannot install new packages, omit `PSYCH_SUITE_AUDIO_KEY` to disable encryption-at-rest.
The app will still run without `cryptography` installed.
