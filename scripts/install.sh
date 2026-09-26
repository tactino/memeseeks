#!/bin/sh
# 迷因捕手 · memeseeks — install on macOS or Linux.
#
#   curl -LsSf https://raw.githubusercontent.com/tactino/memeseeks/main/scripts/install.sh | sh
#
# Options, as environment variables in front of `sh`:
#   MEMESEEKS_DIR     where to install (default: ~/Library/Application Support/memeseeks on macOS,
#                     ~/.local/share/memeseeks on Linux)
#   MEMESEEKS_LIBRARY your memes' index, 图集 and collected images (default: ~/.memeseeks)
#   MEMESEEKS_MODELS  the Hugging Face cache, e.g. one you already have (default: <MEMESEEKS_DIR>/models)
#   MEMESEEKS_MIRROR  auto (default) | on | off: mirrors for PyPI, Python and the models, for China
#   MEMESEEKS_SOURCE  what to install (default: the main branch on GitHub)
#   MEMESEEKS_NO_SHORTCUT=1, MEMESEEKS_NO_LAUNCH=1
#
# Everything goes into that one folder: its own uv, its own Python, the app, and the models (about 3.9 GB,
# fetched on the first start). Nothing is added to your shell's PATH. Uninstalling is deleting the folder
# (and the shortcut); your library stays in ~/.memeseeks. Run it again to update.

set -eu

say() { printf '  %s\n' "$1"; }
step() { printf '\n\033[33m» %s\033[0m\n' "$1"; }
fail() { printf '\n\033[31m%s\033[0m\n' "$1" >&2; exit 1; }

OS=$(uname -s)
if [ "$OS" = "Darwin" ]; then DEFAULT_DIR="$HOME/Library/Application Support/memeseeks"
else DEFAULT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/memeseeks"; fi
DIR=${MEMESEEKS_DIR:-$DEFAULT_DIR}
LIBRARY=${MEMESEEKS_LIBRARY:-}
MODELS=${MEMESEEKS_MODELS:-}
MIRROR=${MEMESEEKS_MIRROR:-auto}
SOURCE=${MEMESEEKS_SOURCE:-https://github.com/tactino/memeseeks/archive/refs/heads/main.zip}
command -v curl >/dev/null 2>&1 || fail "需要 curl"

printf '\n\033[33m迷因捕手 · memeseeks 安装\033[0m\n'
say "程序：$DIR"
say "图库：${LIBRARY:-$HOME/.memeseeks}"
say "模型：${MODELS:-$DIR/models}"
mkdir -p "$DIR"

# ---- mirrors: used when Hugging Face cannot be reached quickly (usually: from China) ----
if [ "$MIRROR" = "auto" ]; then
  if curl -fsSI -m 6 https://huggingface.co/api/models/BAAI/bge-m3 >/dev/null 2>&1; then MIRROR=off; else MIRROR=on; fi
fi
if [ "$MIRROR" = "on" ]; then
  say "使用国内镜像（PyPI：清华；Python：npmmirror；模型：hf-mirror）"
  export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
  export UV_PYTHON_INSTALL_MIRROR=https://registry.npmmirror.com/-/binary/python-build-standalone
fi
export UV_CACHE_DIR="$DIR/cache" UV_PYTHON_INSTALL_DIR="$DIR/python"

# ---- uv, into this folder only ----
UV="$DIR/bin/uv"
if [ ! -x "$UV" ]; then
  step "下载 uv（Python 包管理工具）"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$DIR/bin" UV_NO_MODIFY_PATH=1 sh >/dev/null \
    || fail "uv 下载失败。网络不稳时重新运行一次；也可以先自己装好 uv，再把它放到 $DIR/bin/uv"
fi

# ---- Python 3.12 of its own ----
PY="$DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  step "准备 Python 3.12"
  "$UV" venv --managed-python --python 3.12 "$DIR/.venv" --quiet || fail "创建 Python 环境失败"
fi

# ---- the app; on Linux, PyPI's torch is the CUDA build (several GB), so take the CPU one first ----
step "安装迷因捕手（第一次大约 700 MB，需要几分钟）"
if [ "$OS" = "Linux" ]; then
  "$UV" pip install --python "$PY" torch --index-url https://download.pytorch.org/whl/cpu \
    || fail "安装 torch 失败。网络不稳时重新运行一次即可"
fi
"$UV" pip install --python "$PY" "memeseeks[ml,serve] @ $SOURCE" --reinstall-package memeseeks --refresh-package memeseeks \
  || fail "安装失败。网络不稳时重新运行一次即可，已下载的部分不会重下"
"$UV" cache prune --quiet 2>/dev/null || true

# ---- the launcher (paths relative to itself) and a shortcut ----
LAUNCHER="$DIR/memeseeks"
{
  echo '#!/bin/sh'
  echo '# 迷因捕手: start it; close this terminal (or press Ctrl+C) to stop.'
  echo 'HERE=$(cd "$(dirname "$0")" && pwd)'
  if [ -n "$MODELS" ]; then printf 'export HF_HOME="%s"\n' "$MODELS"; else echo 'export HF_HOME="$HERE/models"'; fi
  if [ -n "$LIBRARY" ]; then printf 'export MEMESEEKS_HOME="%s"\n' "$LIBRARY"; fi
  [ "$MIRROR" = "on" ] && echo 'export HF_ENDPOINT=https://hf-mirror.com'
  echo 'exec "$HERE/.venv/bin/memeseeks" serve --open "$@"'
} > "$LAUNCHER"
chmod +x "$LAUNCHER"
SITE=$("$PY" -c "import memeseeks, os; print(os.path.dirname(memeseeks.__file__))")
cp "$SITE/web/icons/icon-512.png" "$DIR/memeseeks.png"
if [ -z "${MEMESEEKS_NO_SHORTCUT:-}" ]; then
  step "创建快捷方式"
  if [ "$OS" = "Darwin" ]; then
    LINK="$HOME/Desktop/迷因捕手.command"
    printf '#!/bin/sh\nexec "%s"\n' "$LAUNCHER" > "$LINK" && chmod +x "$LINK"
  else
    APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    LINK="$APPS/memeseeks.desktop"
    mkdir -p "$APPS"
    printf '[Desktop Entry]\nType=Application\nName=迷因捕手\nName[en]=memeseeks\nComment=迷因捕手 · memeseeks\nExec="%s"\nIcon=%s\nTerminal=true\nCategories=Graphics;Utility;\n' \
      "$LAUNCHER" "$DIR/memeseeks.png" > "$LINK"
  fi
  say "快捷方式：$LINK"
fi

printf '\n\033[32m装好了。\033[0m\n'
say "以后从快捷方式启动，或者运行：\"$LAUNCHER\"；关掉它的终端就会停止。"
say "第一次启动会下载约 3.9 GB 的模型，网页上能看到进度；下完就能搜索。"
say "卸载：删除 $DIR（和快捷方式）。你的图库在 ${LIBRARY:-~/.memeseeks}，不会被删除。"
if [ -z "${MEMESEEKS_NO_LAUNCH:-}" ]; then exec "$LAUNCHER"; fi
