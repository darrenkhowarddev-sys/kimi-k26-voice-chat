# Kimi K2.6 Voice Chat

Python voice-chat loop:

```text
Microphone -> Whisper STT -> Kimi K2.6 on OpenRouter -> MisoTTS on RunPod -> Speaker
```

MisoTTS is served from your own RunPod RTX 4090 pod through `POST /tts`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On macOS, `sounddevice` may also need PortAudio:

```bash
brew install portaudio
```

Fill in `.env`:

```bash
OPENROUTER_API_KEY=sk-or-...
OPENAI_API_KEY=sk-...
HF_TOKEN=hf_...                 # used on the pod if Hugging Face downloads need auth
MISOTTS_ENDPOINT_URL=https://your-runpod-proxy-url
MISOTTS_API_KEY=
MISOTTS_TIMEOUT_SECONDS=240
```

`.env` is ignored by git. `.env.example` is the committed template.

The literal placeholder values above will not work. Replace all three before running the smoke tests.

To enter keys without echoing them into your shell history:

```bash
python configure_env.py
```

Or configure one key at a time:

```bash
python configure_env.py --openrouter
python configure_env.py --openai
python configure_env.py --hf
python configure_env.py --miso-url
python configure_env.py --miso-key
```

## Deploy MisoTTS On RunPod

Start an RTX 4090 pod with a PyTorch image that has Python 3.10 or newer, then copy or clone this repo onto the pod.

On the pod:

```bash
cd /workspace/kimi-k26-voice-chat
bash deploy_runpod.sh
```

The first launch downloads MisoTTS and related model assets, so expect a slow cold start and make sure the pod has enough disk space. Once loaded, the server exposes:

```bash
GET  /health
POST /tts
```

Local test from your Mac:

```bash
curl -X POST "$MISOTTS_ENDPOINT_URL/tts" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello, I am Kimi."}' \
  --output /tmp/miso.wav
```

## Test Stages

Run each stage before the full loop:

```bash
python test_stt.py
python test_kimi.py
python test_tts.py
```

`test_tts.py` now calls `MISOTTS_ENDPOINT_URL/tts`; it does not use the broken public Hugging Face InferenceClient path.

## Run

Fixed 7-second recording window:

```bash
python kimi-voice-chat.py
```

Push-to-talk:

```bash
python kimi-voice-chat.py --push-to-talk
```

## iPhone Web App

Run the voice gateway:

```bash
uvicorn voice_gateway:app --host 0.0.0.0 --port 8080
```

iPhone microphone access requires HTTPS unless the page is on `localhost`, so expose the gateway with a tunnel such as ngrok or Cloudflare Tunnel:

```bash
ngrok http 8080
```

Open the HTTPS URL on the iPhone. The page records audio in Safari, sends it to `/api/voice`, and plays back the Miso WAV returned by the RunPod endpoint.

## Latency Notes

The current implementation is turn-based: it waits for recording, Whisper, Kimi, full Miso WAV generation, and then playback. It is the right foundation, but it will not feel as immediate as a fully streaming voice system.

To chase Sesame-level conversational feel:

- Keep the RunPod pod warm; cold start can take minutes.
- Use the closest RunPod region available.
- Keep `voice_gateway.py` close to the Miso pod when possible.
- Measure `timing` from `/api/voice`; the web UI shows total seconds per turn.
- Next upgrade: streaming STT, streaming Kimi tokens, and streaming Miso audio chunks.

Custom options:

```bash
python kimi-voice-chat.py \
  --record-secs 10 \
  --system-prompt "You are a witty, brief coding partner." \
  --voice-ref /path/to/reference.wav
```

## Voice Reference Notes

MisoTTS documents prompted local generation with a `Segment` context containing prompt text and prompt audio. The current RunPod `/tts` wrapper only accepts `{"text": "..."}`; `--voice-ref` is intentionally disabled until the server supports prompt-audio upload.
