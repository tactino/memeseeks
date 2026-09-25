#!/usr/bin/env bash
# Run one command on the GPU box inside the project venv. Usage: scripts/remote.sh "python -m pytest -q"
# Needs MEMESEEKS_HOST and MEMESEEKS_REMOTE (environment or the gitignored .memeseeks-dev.env).
set -euo pipefail
ENV_FILE="$(dirname "$0")/../.memeseeks-dev.env"
if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi
HOST="${MEMESEEKS_HOST:?set MEMESEEKS_HOST (see .memeseeks-dev.env.example)}"
REMOTE="${MEMESEEKS_REMOTE:?set MEMESEEKS_REMOTE (see .memeseeks-dev.env.example)}"
ssh "$HOST" "cd ~/$REMOTE/code && export HF_HOME=~/$REMOTE/hf-cache XDG_CACHE_HOME=~/$REMOTE/cache PIP_CACHE_DIR=~/$REMOTE/cache/pip PYTORCH_KERNEL_CACHE_PATH=~/$REMOTE/cache/torch-kernels MEMESEEKS_DATA=~/$REMOTE/data MEMESEEKS_RUNS=~/$REMOTE/runs && source ~/$REMOTE/.venv/bin/activate && $1"
