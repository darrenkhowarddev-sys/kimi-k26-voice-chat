#!/usr/bin/env python3
"""Safely write API keys into the local .env file using hidden prompts."""

from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path

ENV_PATH = Path(".env")
KEYS = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "HF_TOKEN", "MISOTTS_ENDPOINT_URL", "MISOTTS_API_KEY")
DEFAULTS = {
    "OPENROUTER_API_KEY": "sk-or-...",
    "OPENAI_API_KEY": "sk-...",
    "HF_TOKEN": "hf_...",
    "MISOTTS_ENDPOINT_URL": "",
    "MISOTTS_API_KEY": "",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure local API keys without echoing them.")
    parser.add_argument("--openrouter", action="store_true", help="Prompt for OPENROUTER_API_KEY only.")
    parser.add_argument("--openai", action="store_true", help="Prompt for OPENAI_API_KEY only.")
    parser.add_argument("--hf", action="store_true", help="Prompt for HF_TOKEN only.")
    parser.add_argument("--miso-url", action="store_true", help="Prompt for MISOTTS_ENDPOINT_URL only.")
    parser.add_argument("--miso-key", action="store_true", help="Prompt for MISOTTS_API_KEY only.")
    return parser.parse_args()


def read_env() -> dict[str, str]:
    values = DEFAULTS.copy()
    if not ENV_PATH.exists():
        return values

    for line in ENV_PATH.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in KEYS:
            values[key] = value.strip()
    return values


def write_env(values: dict[str, str]) -> None:
    lines = [f"{key}={values[key]}" for key in KEYS]
    ENV_PATH.write_text("\n".join(lines) + "\n")


def selected_keys(args: argparse.Namespace) -> tuple[str, ...]:
    selected = []
    if args.openrouter:
        selected.append("OPENROUTER_API_KEY")
    if args.openai:
        selected.append("OPENAI_API_KEY")
    if args.hf:
        selected.append("HF_TOKEN")
    if args.miso_url:
        selected.append("MISOTTS_ENDPOINT_URL")
    if args.miso_key:
        selected.append("MISOTTS_API_KEY")
    return tuple(selected) if selected else KEYS


def main() -> None:
    args = parse_args()
    values = read_env()

    for key in selected_keys(args):
        current = values.get(key, "")
        suffix = f" [currently set, press Enter to keep]" if current and current != DEFAULTS[key] else ""
        entered = getpass(f"{key}{suffix}: ").strip()
        if entered:
            values[key] = entered

    write_env(values)
    print(".env updated. It is ignored by git.")


if __name__ == "__main__":
    main()
