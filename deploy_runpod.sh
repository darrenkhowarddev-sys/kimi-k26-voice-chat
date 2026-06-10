#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
MISO_TTS_DIR="${MISO_TTS_DIR:-/workspace/MisoTTS}"
PORT="${PORT:-8000}"

echo "==> Kimi/MisoTTS RunPod deploy"
echo "APP_DIR=${APP_DIR}"
echo "MISO_TTS_DIR=${MISO_TTS_DIR}"
echo "PORT=${PORT}"

if [ -f "${APP_DIR}/.env" ]; then
  echo "==> Loading ${APP_DIR}/.env"
  set -a
  # shellcheck disable=SC1091
  source "${APP_DIR}/.env"
  set +a
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

if [ ! -d "${MISO_TTS_DIR}/.git" ]; then
  echo "==> Cloning MisoLabsAI/MisoTTS"
  git clone https://github.com/MisoLabsAI/MisoTTS.git "${MISO_TTS_DIR}"
else
  echo "==> MisoTTS checkout already exists"
fi

cd "${MISO_TTS_DIR}"

echo "==> Creating Python 3.10+ virtualenv"
python3 -m venv .venv
source .venv/bin/activate

echo "==> Upgrading packaging tools"
python -m pip install --upgrade pip setuptools wheel

echo "==> Installing MisoTTS and server dependencies"
python -m pip install -e .
python -m pip install fastapi "uvicorn[standard]" python-multipart

echo "==> Launching MisoTTS FastAPI server"
export MISO_TTS_DIR="${MISO_TTS_DIR}"
export HF_HUB_ETAG_TIMEOUT="${HF_HUB_ETAG_TIMEOUT:-60}"
export HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-60}"
export NO_TORCH_COMPILE="${NO_TORCH_COMPILE:-1}"

exec python -m uvicorn server:app \
  --app-dir "${APP_DIR}" \
  --host 0.0.0.0 \
  --port "${PORT}"
