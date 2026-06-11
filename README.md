# Kimi K2.6 Voice Chat

Python voice-chat loop:

```text
Microphone -> STT -> Kimi K2.6 on OpenRouter -> TTS -> Speaker
```

STT providers (`--stt`, default `auto`):

- **ElevenLabs Scribe** — used automatically when `ELEVENLABS_API_KEY` is set.
- **OpenAI Whisper** (`whisper-1`) — used otherwise. Requires OpenAI credit.

TTS providers (`--tts`, default `auto`):

- **MisoTTS** — used automatically when `MISOTTS_ENDPOINT_URL` is set to a real URL.
  Served from your own RunPod RTX 4090 pod through `POST /tts`. (MisoTTS is NOT available
  through the public Hugging Face Inference API, so self-hosting is the only Miso path.)
- **ElevenLabs** — used when its key is set and no Miso endpoint exists.
- **OpenAI TTS** (`gpt-4o-mini-tts`) — final fallback. Requires OpenAI credit.

Force providers explicitly, e.g. `--stt elevenlabs --tts elevenlabs`, or set
`STT_PROVIDER` / `TTS_PROVIDER` in `.env`.

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

Fill in `.env` (see `.env.example` for the full template):

```bash
OPENROUTER_API_KEY=sk-or-...    # required — Kimi K2.6
ELEVENLABS_API_KEY=...          # easiest working STT+TTS path
OPENAI_API_KEY=sk-...           # only needed for whisper/openai-tts providers
HF_TOKEN=hf_...                 # only used on the RunPod pod for Miso downloads
MISOTTS_ENDPOINT_URL=https://your-runpod-proxy-url   # only for the Miso path
```

`.env` is ignored by git. `OPENROUTER_API_KEY` plus ONE speech provider key
(`ELEVENLABS_API_KEY` or a funded `OPENAI_API_KEY`) is enough to run.

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

`test_tts.py` uses OpenAI TTS by default, or MisoTTS when `MISOTTS_ENDPOINT_URL` is configured.
Force one explicitly: `python test_tts.py openai` or `python test_tts.py miso`.

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
