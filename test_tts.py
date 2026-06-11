#!/usr/bin/env python3
"""Test TTS. Provider auto-selects (miso > elevenlabs > openai) or pass one explicitly:

    python test_tts.py [elevenlabs|openai|miso]
"""

import sys
from pathlib import Path

import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv

load_dotenv()

import speech_providers as speech

TEST_TEXT = "Hello, I am Kimi."

provider = sys.argv[1] if len(sys.argv) > 1 else speech.resolve_tts_provider()
print(f"TTS provider: {provider}")

openai_client = None
if provider == "openai":
    from env_utils import get_required_env
    from openai import OpenAI

    env = get_required_env(["OPENAI_API_KEY"])
    openai_client = OpenAI(api_key=env["OPENAI_API_KEY"])

audio_bytes = speech.synthesize(provider, TEST_TEXT, openai_client=openai_client)

wav_path = Path("/tmp/test_tts.wav")
wav_path.write_bytes(audio_bytes)
data, sample_rate = sf.read(wav_path, dtype="float32")
print(f"Wrote {wav_path} ({len(audio_bytes)} bytes, {len(data) / sample_rate:.1f}s @ {sample_rate}Hz)")
sd.play(data, sample_rate)
sd.wait()
