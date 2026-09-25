#!/usr/bin/env bash
# One-time environment setup on the GPU box. Everything stays under ~/<remote dir>.
# Usage (on the box): bash setup_remote.sh <remote dir relative to ~, e.g. work/memeseeks>
set -euo pipefail
R="$HOME/${1:?usage: setup_remote.sh <remote dir relative to ~>}"
cd "$R"
# Keep pip/torch/HF caches inside the project folder, never in the account's ~/.cache
export XDG_CACHE_HOME=$R/cache PIP_CACHE_DIR=$R/cache/pip HF_HOME=$R/hf-cache
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -e "code[ml,serve,dev]"
pip freeze > code-env.lock.txt
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
