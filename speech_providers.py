"""Shared STT/TTS provider layer.

STT providers: openai (whisper-1), elevenlabs (scribe_v1)
TTS providers: openai (gpt-4o-mini-tts), elevenlabs, miso (self-hosted RunPod /tts)

All TTS functions return WAV bytes ready for playback or browser delivery.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
DEFAULT_ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel
DEFAULT_ELEVENLABS_TTS_MODEL = "eleven_turbo_v2_5"
ELEVENLABS_PCM_SAMPLE_RATE = 22050

DEFAULT_OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_OPENAI_TTS_VOICE = "alloy"

MISO_PLACEHOLDER = "https://your-runpod-proxy-url"


def _env(key: str) -> str:
    return os.getenv(key, "").strip()


def misotts_endpoint_configured() -> bool:
    value = _env("MISOTTS_ENDPOINT_URL")
    return bool(value) and value != MISO_PLACEHOLDER


def elevenlabs_configured() -> bool:
    return bool(_env("ELEVENLABS_API_KEY"))


def resolve_tts_provider(requested: str = "auto") -> str:
    """auto -> TTS_PROVIDER env, else miso when its endpoint is set,
    else elevenlabs when its key is set, else openai."""
    if requested != "auto":
        return requested
    env_choice = _env("TTS_PROVIDER").lower()
    if env_choice and env_choice != "auto":
        return env_choice
    if misotts_endpoint_configured():
        return "miso"
    if elevenlabs_configured():
        return "elevenlabs"
    return "openai"


def resolve_stt_provider(requested: str = "auto") -> str:
    """auto -> STT_PROVIDER env, else elevenlabs when its key is set, else openai."""
    if requested != "auto":
        return requested
    env_choice = _env("STT_PROVIDER").lower()
    if env_choice and env_choice != "auto":
        return env_choice
    if elevenlabs_configured():
        return "elevenlabs"
    return "openai"


# --- STT ---------------------------------------------------------------


def transcribe_openai(openai_client, audio_path: Path) -> str:
    with Path(audio_path).open("rb") as audio_file:
        result = openai_client.audio.transcriptions.create(model="whisper-1", file=audio_file)
    return result.text.strip()


def transcribe_elevenlabs(audio_path: Path) -> str:
    api_key = _env("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set.")
    audio_path = Path(audio_path)
    with audio_path.open("rb") as audio_file:
        response = requests.post(
            f"{ELEVENLABS_BASE_URL}/speech-to-text",
            headers={"xi-api-key": api_key},
            files={"file": (audio_path.name, audio_file)},
            data={"model_id": os.getenv("ELEVENLABS_STT_MODEL", "scribe_v1")},
            timeout=120,
        )
    response.raise_for_status()
    return response.json().get("text", "").strip()


def transcribe(provider: str, audio_path: Path, openai_client=None) -> str:
    if provider == "elevenlabs":
        return transcribe_elevenlabs(audio_path)
    if provider == "openai":
        if openai_client is None:
            raise RuntimeError("OpenAI client required for openai STT.")
        return transcribe_openai(openai_client, audio_path)
    raise ValueError(f"Unknown STT provider: {provider}")


# --- TTS ---------------------------------------------------------------


def synthesize_openai(openai_client, text: str, voice: str | None = None) -> bytes:
    response = openai_client.audio.speech.create(
        model=os.getenv("OPENAI_TTS_MODEL", DEFAULT_OPENAI_TTS_MODEL),
        voice=voice or os.getenv("OPENAI_TTS_VOICE", DEFAULT_OPENAI_TTS_VOICE),
        input=text,
        response_format="wav",
    )
    return response.content


def synthesize_elevenlabs(text: str, voice_id: str | None = None) -> bytes:
    api_key = _env("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set.")
    voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_ELEVENLABS_VOICE_ID)
    response = requests.post(
        f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}",
        params={"output_format": f"pcm_{ELEVENLABS_PCM_SAMPLE_RATE}"},
        headers={"xi-api-key": api_key},
        json={
            "text": text,
            "model_id": os.getenv("ELEVENLABS_TTS_MODEL", DEFAULT_ELEVENLABS_TTS_MODEL),
        },
        timeout=120,
    )
    response.raise_for_status()
    pcm = np.frombuffer(response.content, dtype=np.int16)
    buffer = io.BytesIO()
    sf.write(buffer, pcm, ELEVENLABS_PCM_SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def misotts_tts_url(endpoint_url: str) -> str:
    base_url = endpoint_url.rstrip("/")
    return base_url if base_url.endswith("/tts") else f"{base_url}/tts"


def synthesize_miso(text: str) -> bytes:
    endpoint_url = _env("MISOTTS_ENDPOINT_URL")
    if not misotts_endpoint_configured():
        raise RuntimeError("MISOTTS_ENDPOINT_URL is not configured.")
    headers = {}
    api_key = _env("MISOTTS_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.post(
        misotts_tts_url(endpoint_url),
        json={"text": text},
        headers=headers,
        timeout=int(os.getenv("MISOTTS_TIMEOUT_SECONDS", "240")),
    )
    response.raise_for_status()
    return response.content


def synthesize(provider: str, text: str, openai_client=None, voice: str | None = None) -> bytes:
    if provider == "miso":
        return synthesize_miso(text)
    if provider == "elevenlabs":
        return synthesize_elevenlabs(text, voice_id=voice)
    if provider == "openai":
        if openai_client is None:
            raise RuntimeError("OpenAI client required for openai TTS.")
        return synthesize_openai(openai_client, text, voice=voice)
    raise ValueError(f"Unknown TTS provider: {provider}")
