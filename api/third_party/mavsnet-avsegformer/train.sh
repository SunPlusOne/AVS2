SESSION=$1
CONFIG=$2

export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-max_split_size_mb:128}

PYTHONPATH="$(dirname $0)/..":$PYTHONPATH \
python scripts/$SESSION/train.py $CONFIG "${@:3}"
