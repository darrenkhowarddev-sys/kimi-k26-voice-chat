#!/usr/bin/env python3
"""FastAPI gateway for the iPhone web app.

The browser records audio and posts it here. This server keeps API keys private,
then runs: STT (ElevenLabs Scribe or OpenAI Whisper) -> Kimi K2.6 ->
TTS (ElevenLabs, OpenAI, or RunPod MisoTTS when MISOTTS_ENDPOINT_URL is configured).
"""

from __future__ import annotations

import base64
import os
import tempfile
import time
from pathlib import Path
from typing import Optional
from uuid import uuid4

from dotenv import load_dotenv

import speech_providers as speech
from env_utils import get_required_env
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI

load_dotenv()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
KIMI_MODEL = os.getenv("KIMI_MODEL", "moonshotai/kimi-k2.6")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are Kimi, a warm, concise voice companion. Keep replies brief and natural.",
)
MAX_EXCHANGES = int(os.getenv("MAX_EXCHANGES", "10"))
WEB_DIR = Path(__file__).parent / "web"

STT_PROVIDER = speech.resolve_stt_provider()
TTS_PROVIDER = speech.resolve_tts_provider()

required_keys = ["OPENROUTER_API_KEY"]
if "openai" in (STT_PROVIDER, TTS_PROVIDER):
    required_keys.append("OPENAI_API_KEY")
if "elevenlabs" in (STT_PROVIDER, TTS_PROVIDER):
    required_keys.append("ELEVENLABS_API_KEY")
if TTS_PROVIDER == "miso":
    required_keys.append("MISOTTS_ENDPOINT_URL")
env = get_required_env(required_keys)
openai_client = OpenAI(api_key=env["OPENAI_API_KEY"]) if env.get("OPENAI_API_KEY") else None
kimi_client = OpenAI(
    api_key=env["OPENROUTER_API_KEY"],
    base_url=OPENROUTER_BASE_URL,
    default_headers={
        "HTTP-Referer": os.getenv("OPENROUTER_APP_URL", "https://localhost"),
        "X-Title": os.getenv("OPENROUTER_APP_TITLE", "Kimi iPhone Voice Chat"),
    },
)
history_by_session: dict[str, list[dict[str, str]]] = {}

app = FastAPI(title="Kimi iPhone Voice Gateway")


def trim_history(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    system_messages = [message for message in messages if message["role"] == "system"]
    conversational_messages = [message for message in messages if message["role"] != "system"]
    return system_messages[:1] + conversational_messages[-MAX_EXCHANGES * 2 :]


def session_history(session_id: str) -> list[dict[str, str]]:
    if session_id not in history_by_session:
        history_by_session[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return history_by_session[session_id]


def transcribe_upload(audio: UploadFile) -> str:
    suffix = Path(audio.filename or "speech.webm").suffix or ".webm"
    temp = tempfile.NamedTemporaryFile(prefix="iphone_speech_", suffix=suffix, delete=False)
    temp_path = Path(temp.name)
    try:
        temp.write(audio.file.read())
        temp.close()
        return speech.transcribe(STT_PROVIDER, temp_path, openai_client=openai_client)
    finally:
        temp_path.unlink(missing_ok=True)


def ask_kimi(session_id: str, transcript: str) -> str:
    history = session_history(session_id)
    history.append({"role": "user", "content": transcript})
    history = trim_history(history)
    response = kimi_client.chat.completions.create(model=KIMI_MODEL, messages=history)
    reply = response.choices[0].message.content or "I did not get a response back."
    reply = reply.strip()
    history.append({"role": "assistant", "content": reply})
    history_by_session[session_id] = trim_history(history)
    return reply


def synthesize(reply: str) -> bytes:
    return speech.synthesize(TTS_PROVIDER, reply, openai_client=openai_client)


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse(
        {"ok": True, "sessions": len(history_by_session), "stt": STT_PROVIDER, "tts": TTS_PROVIDER}
    )


@app.post("/api/voice")
def voice(
    session_id: Optional[str] = Form(default=None),
    audio: UploadFile = File(...),
) -> JSONResponse:
    session_id = session_id or str(uuid4())
    started_at = time.perf_counter()
    try:
        stt_started_at = time.perf_counter()
        transcript = transcribe_upload(audio)
        stt_seconds = time.perf_counter() - stt_started_at
        if not transcript:
            raise HTTPException(status_code=400, detail="No speech detected")
        kimi_started_at = time.perf_counter()
        reply = ask_kimi(session_id, transcript)
        kimi_seconds = time.perf_counter() - kimi_started_at
        tts_started_at = time.perf_counter()
        wav_bytes = synthesize(reply)
        tts_seconds = time.perf_counter() - tts_started_at
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(
        {
            "session_id": session_id,
            "transcript": transcript,
            "reply": reply,
            "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
            "timing": {
                "stt_seconds": round(stt_seconds, 3),
                "kimi_seconds": round(kimi_seconds, 3),
                "tts_seconds": round(tts_seconds, 3),
                "total_seconds": round(time.perf_counter() - started_at, 3),
            },
        }
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
