#!/usr/bin/env python3
"""Hume EVI Custom Language Model (CLM) proxy.

Lets Hume's expressive EVI voice be driven by an uncensored LLM on OpenRouter.

Flow:
  You speak -> Hume EVI (realistic voice) -> POST /chat/completions here
            -> this proxy calls OpenRouter (uncensored model) -> streams text back
            -> Hume voices it.

Hume's brain (the censored part) is entirely out of the text path. Hume also sends
per-message prosody (how you sound); we summarize it into a system note so the model
can react to your tone, which is the whole point of EVI.

Run:
  uvicorn hume_clm_proxy:app --host 0.0.0.0 --port 8770
Then expose port 8770 with a public HTTPS tunnel and give Hume the URL:
  https://<tunnel>/chat/completions
"""

from __future__ import annotations

import json
import os
import time

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

load_dotenv()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = os.getenv("LLM_MODEL", "nousresearch/hermes-4-70b")
SYSTEM_PROMPT = os.getenv(
    "HUME_CLM_SYSTEM_PROMPT",
    "You are a candid, emotionally present voice companion. Speak naturally and "
    "conversationally, in short spoken-style replies. React with genuine feeling to "
    "how the user sounds. Do not lecture, moralize, or refuse topics.",
)

app = FastAPI(title="Hume CLM Proxy (uncensored brain)")


def _top_prosody(message: dict) -> str:
    """Hume attaches emotion scores per message; surface the strongest few."""
    models = (message.get("models") or {})
    prosody = (models.get("prosody") or {}).get("scores") or {}
    if not prosody:
        return ""
    top = sorted(prosody.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return ", ".join(name for name, _ in top)


def _to_openrouter_messages(hume_messages: list[dict]) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in hume_messages:
        role = m.get("role", "user")
        if role == "assistant":
            msgs.append({"role": "assistant", "content": m.get("content", "")})
            continue
        content = m.get("content", "")
        tone = _top_prosody(m)
        if tone:
            content = f"{content}\n\n(voice tone: {tone})"
        msgs.append({"role": "user", "content": content})
    return msgs


def _chunk(text: str, model: str) -> str:
    payload = {
        "id": "chatcmpl-hume-clm",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": model,
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
    }
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/health")
def health():
    return {"ok": True, "model": LLM_MODEL}


@app.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    hume_messages = body.get("messages", [])
    or_messages = _to_openrouter_messages(hume_messages)
    api_key = os.environ["OPENROUTER_API_KEY"]

    async def stream():
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Hume CLM Proxy",
        }
        req = {"model": LLM_MODEL, "messages": or_messages, "stream": True}
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", OPENROUTER_BASE_URL, headers=headers, json=req) as r:
                    async for line in r.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                            delta = obj["choices"][0]["delta"].get("content")
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                        if delta:
                            yield _chunk(delta, LLM_MODEL)
        except Exception as exc:  # surface errors as spoken text rather than a dead stream
            yield _chunk(f"Proxy error: {exc}", LLM_MODEL)
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
