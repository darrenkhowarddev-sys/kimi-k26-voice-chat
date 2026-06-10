#!/usr/bin/env python3
"""Test MisoTTS through the RunPod /tts endpoint."""

import os
from pathlib import Path

import requests
import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv
from env_utils import get_required_env

load_dotenv()


def misotts_tts_url(endpoint_url: str) -> str:
    base_url = endpoint_url.rstrip("/")
    return base_url if base_url.endswith("/tts") else f"{base_url}/tts"


env = get_required_env(["MISOTTS_ENDPOINT_URL"])
headers = {}
api_key = os.getenv("MISOTTS_API_KEY", "").strip()
if api_key:
    headers["Authorization"] = f"Bearer {api_key}"

response = requests.post(
    misotts_tts_url(env["MISOTTS_ENDPOINT_URL"]),
    json={"text": "Hello, I am Kimi."},
    headers=headers,
    timeout=240,
)
response.raise_for_status()
audio_bytes = response.content

wav_path = Path("/tmp/test_tts.wav")
wav_path.write_bytes(audio_bytes)
data, sample_rate = sf.read(wav_path, dtype="float32")
sd.play(data, sample_rate)
sd.wait()
