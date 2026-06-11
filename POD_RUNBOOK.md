# MisoTTS RunPod Runbook

Working as of 2026-06-11. First successful end-to-end: ElevenLabs Scribe STT ->
Kimi K2.6 (OpenRouter) -> MisoTTS on RunPod.

## Live pod

| | |
|---|---|
| Pod | `2vgbb5qzdzwmgb` (`miso-tts-8b`) |
| GPU | RTX A5000 24GB, secure cloud, **$0.27/hr while running** |
| Account | darrenkhoward.dev@gmail.com workspace (NOT the browser-default workspace) |
| TTS endpoint | `https://2vgbb5qzdzwmgb-8000.proxy.runpod.net/tts` |
| SSH | `ssh -p 22191 -i ~/.ssh/id_ed25519 root@69.30.85.178` (port/IP change on every pod restart — re-check via API) |
| Server log | `/workspace/miso_server.log` on the pod |
| Model cache | `/workspace/.cache/huggingface` (~32GB, persists on the 60GB volume) |

There are TWO RunPod accounts: the browser console logs into one (has the two old
stopped pods `working_turquoise_fox` / `balanced_peach_damselfly`), the Miso pod lives
in the other. API keys: archived key in chat-archive (personal workspace);
`~/.runpod_key_workspace2` (browser workspace, created 2026-06-11).

## Stop / start the pod (controls billing)

```bash
KEY=<personal-workspace rpa_ key>
# stop (model cache survives on the volume; storage costs ~$0.01/hr)
curl -X POST -H "Authorization: Bearer $KEY" https://rest.runpod.io/v1/pods/2vgbb5qzdzwmgb/stop
# start again later
curl -X POST -H "Authorization: Bearer $KEY" https://rest.runpod.io/v1/pods/2vgbb5qzdzwmgb/start
```

After a restart: SSH ip/port change (query `GET /v1/pods/2vgbb5qzdzwmgb`), then
run `bash /tmp/start_miso.sh` on the pod (or recreate it — see below). The proxy
URL stays the same. Model loads from cache in ~4 minutes.

## Start the TTS server on the pod

```bash
ssh -p <port> -i ~/.ssh/id_ed25519 root@<ip> 'bash /tmp/start_miso.sh'
# wait ~4 min (model load), then:
curl https://2vgbb5qzdzwmgb-8000.proxy.runpod.net/health
```

`/tmp/start_miso.sh` lives on the pod's container disk and is recreated by the
install flow if missing. It reads the HF token from `/workspace/.hf_token`.

## Hard-won gotchas (cost a full day — do not rediscover)

1. **RunPod env vars do NOT reach SSH sessions.** `HF_TOKEN` set at pod creation
   is invisible to SSH-launched processes -> gated `meta-llama/Llama-3.2-1B`
   tokenizer download fails with 401 -> server 500s. This was the root cause of
   the original "Internal Server Error". Fix: export the token explicitly in the
   start script (reads `/workspace/.hf_token`).
2. **pkill self-match.** Running `ssh pod 'pkill -f "uvicorn server:app"; ... nohup uvicorn ...'`
   kills its own parent shell (the pattern is in the ssh command line) before the
   server starts. Always start/stop via a script FILE on the pod.
3. **moshi pins `torch<2.7`** but the RunPod image ships torch 2.8 nightlies.
   Install `moshi` and `silentcipher` with `--no-deps`, then manually install
   their real runtime deps (see `/tmp/miso_pod_fix.sh` flow): einops, sphn,
   sentencepiece, sounddevice, pydub, Flask, pyaml, omegaconf, datasets, tiktoken, etc.
4. `torchtune==0.4.0` + `torchao==0.9.0` must be `--no-deps` too.
5. `/workspace` is network storage (MooseFS) — imports from the venv there are
   slow (minutes). Be patient on first start; don't assume it's hung.

## Performance reality (A5000)

~6s of generation time per 1s of audio (50s for an 8.5s sentence). Fine for
proving the chain; for snappier conversation move the pod to a 4090 (~2-3x faster)
or accept the latency. The hosted Miso API's 110ms TTFB is H100-class hardware —
not achievable on consumer GPUs with this repo's unoptimized inference path.

## Local voice chat usage

`.env` has `MISOTTS_ENDPOINT_URL` set -> TTS auto-resolves to `miso`.

```bash
cd /Users/personal/Projects/kimi-k26-voice-chat
source .venv/bin/activate
python kimi-voice-chat.py --push-to-talk          # Miso voice (slow, real)
python kimi-voice-chat.py --push-to-talk --tts elevenlabs   # fast fallback
```
