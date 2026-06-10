#!/usr/bin/env python3
"""FastAPI wrapper for a local MisoTTS checkout on RunPod."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
os.environ.setdefault("NO_TORCH_COMPILE", "1")

MISO_TTS_DIR = Path(os.getenv("MISO_TTS_DIR", "/workspace/MisoTTS"))
if MISO_TTS_DIR.exists():
    sys.path.insert(0, str(MISO_TTS_DIR))

import torch
import torchaudio
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from generator import DEFAULT_MISO_TTS_REPO_ID, load_miso_8b
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    speaker: int = Field(default=0, ge=0)
    max_audio_length_ms: int = Field(default=15000, ge=1000, le=90000)
    temperature: float = Field(default=0.9, ge=0.1, le=2.0)
    topk: int = Field(default=50, ge=1, le=500)


app = FastAPI(title="MisoTTS RunPod Server")
_generator = None
_generator_lock = threading.Lock()


def get_generator():
    global _generator
    if _generator is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model_source = os.getenv("MISO_TTS_8B_MODEL", DEFAULT_MISO_TTS_REPO_ID)
        print(f"Loading MisoTTS on {device} from {model_source}", flush=True)
        _generator = load_miso_8b(device=device, model_path_or_repo_id=model_source)
        print("MisoTTS loaded", flush=True)
    return _generator


@app.on_event("startup")
def warm_model() -> None:
    if os.getenv("MISO_WARM_ON_STARTUP", "1") == "1":
        get_generator()


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "cuda": torch.cuda.is_available(),
            "device": "cuda" if torch.cuda.is_available() else "cpu",
            "model_loaded": _generator is not None,
        }
    )


def cleanup_file(path: Path) -> None:
    path.unlink(missing_ok=True)


def require_api_key(authorization: str | None) -> None:
    expected = os.getenv("MISOTTS_API_KEY", "").strip()
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid or missing MISOTTS_API_KEY bearer token")


@app.post("/tts")
def tts(request: TTSRequest, authorization: str | None = Header(default=None)) -> FileResponse:
    require_api_key(authorization)
    generator = get_generator()
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text must not be empty")

    try:
        started_at = time.perf_counter()
        with _generator_lock:
            audio = generator.generate(
                text=text,
                speaker=request.speaker,
                context=[],
                max_audio_length_ms=request.max_audio_length_ms,
                temperature=request.temperature,
                topk=request.topk,
            )
        generation_seconds = time.perf_counter() - started_at
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MisoTTS generation failed: {exc}") from exc

    temp = tempfile.NamedTemporaryFile(prefix="misotts_", suffix=".wav", delete=False)
    temp_path = Path(temp.name)
    temp.close()

    try:
        torchaudio.save(
            str(temp_path),
            audio.detach().float().cpu().unsqueeze(0),
            generator.sample_rate,
        )
    except Exception as exc:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"WAV encoding failed: {exc}") from exc

    return FileResponse(
        temp_path,
        media_type="audio/wav",
        filename="miso.wav",
        background=BackgroundTask(cleanup_file, temp_path),
        headers={"X-Miso-Generate-Seconds": f"{generation_seconds:.3f}"},
    )
