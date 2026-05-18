#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${AVS_MAVSNET_ENV_DIR:-$PROJECT_DIR/.venv-mavsnet}"
REPO_DIR="${AVS_MAVSNET_ROOT:-$PROJECT_DIR/api/third_party/mavsnet-avsegformer}"

resolve_python38() {
  if [[ -n "${AVS_MAVSNET_PYTHON:-}" ]]; then
    echo "$AVS_MAVSNET_PYTHON"
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

  echo "[ERROR] Python 3.8 not found. Set AVS_MAVSNET_PYTHON to a Python 3.8 executable." >&2
  return 1
}

if [[ ! -d "$REPO_DIR" ]]; then
  echo "[ERROR] MAVS-Net repo not found at $REPO_DIR" >&2
  echo "        Put your MAVS-Net code under api/third_party/mavsnet-avsegformer or set AVS_MAVSNET_ROOT." >&2
  exit 1
fi

if [[ ! -d "$REPO_DIR/ops" ]]; then
  echo "[ERROR] MAVS-Net ops directory not found at $REPO_DIR/ops" >&2
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

echo "[OK] MAVS-Net environment ready: $VENV_DIR"
