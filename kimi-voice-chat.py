#!/usr/bin/env python3
"""Voice chat loop: microphone -> STT -> Kimi K2.6 -> TTS -> speaker.

STT: ElevenLabs Scribe or OpenAI Whisper.
TTS: ElevenLabs, OpenAI, or self-hosted MisoTTS (RunPod).
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv

import speech_providers as speech
from env_utils import get_required_env
from openai import OpenAI

load_dotenv()


DEFAULT_SYSTEM_PROMPT = (
    "You are Kimi, a warm, concise voice companion. Keep replies conversational "
    "and short enough to be spoken aloud comfortably."
)
DEFAULT_KIMI_MODEL = "moonshotai/kimi-k2.6"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Talk to Kimi K2.6 with voice in and voice out."
    )
    parser.add_argument("--record-secs", type=int, default=7, help="Seconds to record per turn.")
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT, help="Persona/system prompt.")
    parser.add_argument("--voice-ref", type=Path, help="Optional .wav reference voice clip (miso only).")
    parser.add_argument("--push-to-talk", action="store_true", help="Press Enter to start/stop recording.")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Microphone sample rate.")
    parser.add_argument("--kimi-model", default=DEFAULT_KIMI_MODEL, help="OpenRouter model id.")
    parser.add_argument(
        "--stt",
        choices=["auto", "openai", "elevenlabs"],
        default="auto",
        help="STT provider. auto = elevenlabs when its key is set, otherwise openai whisper.",
    )
    parser.add_argument(
        "--tts",
        choices=["auto", "openai", "elevenlabs", "miso"],
        default="auto",
        help="TTS provider. auto = miso when MISOTTS_ENDPOINT_URL is set, "
        "else elevenlabs when its key is set, else openai.",
    )
    parser.add_argument(
        "--voice",
        default=None,
        help="Voice override: ElevenLabs voice_id, or OpenAI voice name (alloy, nova, ...).",
    )
    parser.add_argument(
        "--max-exchanges",
        type=int,
        default=10,
        help="Keep this many user/assistant exchanges plus the system prompt.",
    )
    return parser.parse_args()


def make_openrouter_client(api_key: str) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": os.getenv("OPENROUTER_APP_URL", "https://localhost"),
            "X-Title": os.getenv("OPENROUTER_APP_TITLE", "Kimi Voice Chat"),
        },
    )


def record_audio_fixed(record_secs: int, sample_rate: int) -> np.ndarray:
    print(f"\nRecording for {record_secs}s...")
    audio = sd.rec(
        int(record_secs * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return audio


def record_audio_push_to_talk(sample_rate: int) -> np.ndarray:
    frames: list[np.ndarray] = []

    def callback(indata: np.ndarray, _frame_count: int, _time_info: object, status: sd.CallbackFlags) -> None:
        if status:
            print(f"Audio input warning: {status}")
        frames.append(indata.copy())

    input("\nPress Enter to speak...")
    print("Recording. Press Enter to stop.")
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32", callback=callback):
        input()

    if not frames:
        return np.zeros((0, 1), dtype=np.float32)

    return np.concatenate(frames, axis=0)


def write_temp_wav(audio: np.ndarray, sample_rate: int) -> Path:
    temp = tempfile.NamedTemporaryFile(prefix="kimi_turn_", suffix=".wav", delete=False)
    temp_path = Path(temp.name)
    temp.close()
    sf.write(temp_path, audio, sample_rate)
    return temp_path


def trim_history(messages: list[dict[str, str]], max_exchanges: int) -> list[dict[str, str]]:
    system_messages = [message for message in messages if message["role"] == "system"]
    conversational_messages = [message for message in messages if message["role"] != "system"]
    return system_messages[:1] + conversational_messages[-max_exchanges * 2 :]


def ask_kimi(client: OpenAI, model: str, history: list[dict[str, str]]) -> str:
    response = client.chat.completions.create(model=model, messages=history)
    content = response.choices[0].message.content
    return content.strip() if content else "I did not get a response back."


def play_audio_bytes(audio_bytes: bytes) -> None:
    temp = tempfile.NamedTemporaryFile(prefix="kimi_tts_", suffix=".wav", delete=False)
    temp_path = Path(temp.name)
    temp.write(audio_bytes)
    temp.close()

    try:
        data, sample_rate = sf.read(temp_path, dtype="float32")
        sd.play(data, sample_rate)
        sd.wait()
    finally:
        temp_path.unlink(missing_ok=True)


def should_exit(text: str) -> bool:
    lowered = text.lower()
    return "goodbye" in lowered or "bye kimi" in lowered


def main() -> None:
    args = parse_args()
    stt_provider = speech.resolve_stt_provider(args.stt)
    tts_provider = speech.resolve_tts_provider(args.tts)

    required_keys = ["OPENROUTER_API_KEY"]
    if "openai" in (stt_provider, tts_provider):
        required_keys.append("OPENAI_API_KEY")
    if "elevenlabs" in (stt_provider, tts_provider):
        required_keys.append("ELEVENLABS_API_KEY")
    if tts_provider == "miso":
        required_keys.append("MISOTTS_ENDPOINT_URL")
    env = get_required_env(required_keys)

    if args.voice_ref and tts_provider != "miso":
        raise SystemExit("--voice-ref requires the MisoTTS endpoint (--tts miso).")

    openai_client = (
        OpenAI(api_key=env["OPENAI_API_KEY"]) if "OPENAI_API_KEY" in env and env["OPENAI_API_KEY"] else None
    )
    kimi_client = make_openrouter_client(env["OPENROUTER_API_KEY"])
    history = [{"role": "system", "content": args.system_prompt}]

    print(
        f"Kimi voice chat is ready (STT: {stt_provider}, TTS: {tts_provider}). "
        "Say 'goodbye' to exit, or press Ctrl+C."
    )
    try:
        while True:
            wav_path: Path | None = None
            try:
                audio = (
                    record_audio_push_to_talk(args.sample_rate)
                    if args.push_to_talk
                    else record_audio_fixed(args.record_secs, args.sample_rate)
                )

                if audio.size == 0:
                    print("No audio captured. Try again.")
                    continue

                wav_path = write_temp_wav(audio, args.sample_rate)
                transcript = speech.transcribe(stt_provider, wav_path, openai_client=openai_client)
                if not transcript:
                    print("No speech detected. Try again.")
                    continue

                print(f"You: {transcript}")
                if should_exit(transcript):
                    print("Exiting. Bye.")
                    break

                history.append({"role": "user", "content": transcript})
                history = trim_history(history, args.max_exchanges)

                reply = ask_kimi(kimi_client, args.kimi_model, history)
                print(f"Kimi: {reply}")

                history.append({"role": "assistant", "content": reply})
                history = trim_history(history, args.max_exchanges)

                audio_bytes = speech.synthesize(
                    tts_provider, reply, openai_client=openai_client, voice=args.voice
                )
                play_audio_bytes(audio_bytes)
            except Exception as exc:
                print(f"Turn failed: {exc}")
            finally:
                if wav_path:
                    wav_path.unlink(missing_ok=True)
    except KeyboardInterrupt:
        print("\nExiting. Bye.")


if __name__ == "__main__":
    main()
