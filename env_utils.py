"""Environment helpers shared by the voice-chat scripts."""

from __future__ import annotations

import os
from typing import Iterable

PLACEHOLDER_VALUES = {
    "sk-or-...",
    "sk-...",
    "hf_...",
    "https://your-runpod-proxy-url",
    "https://your-misotts-endpoint",
}


def get_required_env(keys: Iterable[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    missing: list[str] = []

    for key in keys:
        value = os.getenv(key, "").strip()
        if not value or value in PLACEHOLDER_VALUES:
            missing.append(key)
        values[key] = value

    if missing:
        raise SystemExit(
            "Missing real credentials for: "
            + ", ".join(missing)
            + ". Edit .env, replace the placeholder values, and try again."
        )

    return values
