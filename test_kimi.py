#!/usr/bin/env python3
"""Test Kimi K2.6 through OpenRouter."""

from dotenv import load_dotenv
from env_utils import get_required_env
from openai import OpenAI

load_dotenv()

env = get_required_env(["OPENROUTER_API_KEY"])
client = OpenAI(
    api_key=env["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
    default_headers={"HTTP-Referer": "https://localhost", "X-Title": "Test"},
)

response = client.chat.completions.create(
    model="moonshotai/kimi-k2.6",
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
)
print(response.choices[0].message.content)
