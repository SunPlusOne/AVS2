#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${AVS_AVSEGFORMER_ENV_DIR:-$PROJECT_DIR/.venv-avsegformer}"
REPO_DIR="${AVS_AVSEGFORMER_ROOT:-$PROJECT_DIR/api/third_party/AVSegFormer}"

resolve_python38() {
  if [[ -n "${AVS_AVSEGFORMER_PYTHON:-}" ]]; then
    echo "$AVS_AVSEGFORMER_PYTHON"
    return 0
  fi
  if command -v python3.8 >/dev/null 2>&1; then
    command -v python3.8
    return 0
  fi
  if [[ -x "/root/miniconda3/bin/python3.8" ]]; then
    echo "/root/miniconda3/bin/python3.8"
    return 0
  fi

  echo "[ERROR] Python 3.8 not found. Set AVS_AVSEGFORMER_PYTHON to a Python 3.8 executable." >&2
  return 1
}

if [[ ! -d "$REPO_DIR/ops" ]]; then
  echo "[ERROR] AVSegFormer repo not found at $REPO_DIR" >&2
  exit 1
fi

PYTHON38="$(resolve_python38)"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON38" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel ninja
python -m pip install torch==1.10.0+cu111 torchvision==0.11.1+cu111 torchaudio==0.10.0 -f https://download.pytorch.org/whl/torch_stable.html
python -m pip install mmcv-full==1.7.2 -f https://download.openmmlab.com/mmcv/dist/cu111/torch1.10.0/index.html
python -m pip install pandas timm resampy soundfile opencv-python-headless imageio-ffmpeg

cd "$REPO_DIR/ops"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}" FORCE_CUDA=1 python setup.py build install

echo "[OK] AVSegFormer environment ready: $VENV_DIR"