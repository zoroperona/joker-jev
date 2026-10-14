#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! command -v uv >/dev/null 2>&1; then
  echo '请先安装 uv：https://docs.astral.sh/uv/getting-started/installation/' >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  if [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ]; then
    uv python install cpython-3.11-macos-aarch64-none
    uv venv .venv --python cpython-3.11-macos-aarch64-none
  else
    uv venv .venv --python 3.11
  fi
fi
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python download_models.py
printf '\n已准备好预训练模型，无需训练。启动：bash games/doudizhu/start.sh\n'
