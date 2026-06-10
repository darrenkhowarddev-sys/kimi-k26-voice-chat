#!/usr/bin/env python3
"""Record 5 seconds and test OpenAI Whisper transcription."""

import os
from pathlib import Path

import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv
from env_utils import get_required_env
from openai import OpenAI

load_dotenv()

env = get_required_env(["OPENAI_API_KEY"])
client = OpenAI(api_key=env["OPENAI_API_KEY"])
audio = sd.rec(int(5 * 16000), samplerate=16000, channels=1, dtype="float32")
sd.wait()
wav_path = Path("/tmp/test.wav")
sf.write(wav_path, audio, 16000)

with wav_path.open("rb") as audio_file:
    result = client.audio.transcriptions.create(model="whisper-1", file=audio_file)

print("Transcript:", result.text)
