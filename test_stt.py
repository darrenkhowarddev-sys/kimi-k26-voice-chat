#!/usr/bin/env python3
"""Test STT: records 5 seconds from the microphone and transcribes it.

    python test_stt.py [elevenlabs|openai]
"""

import sys

import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv

load_dotenv()

import speech_providers as speech

provider = sys.argv[1] if len(sys.argv) > 1 else speech.resolve_stt_provider()
print(f"STT provider: {provider}")

openai_client = None
if provider == "openai":
    from env_utils import get_required_env
    from openai import OpenAI

    env = get_required_env(["OPENAI_API_KEY"])
    openai_client = OpenAI(api_key=env["OPENAI_API_KEY"])

print("Recording 5 seconds — speak now...")
audio = sd.rec(int(5 * 16000), samplerate=16000, channels=1, dtype="float32")
sd.wait()
sf.write("/tmp/test_stt.wav", audio, 16000)

transcript = speech.transcribe(provider, "/tmp/test_stt.wav", openai_client=openai_client)
print("Transcript:", transcript)
