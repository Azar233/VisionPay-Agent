#!/usr/bin/env bash
#SBATCH --job-name=sx_visionpay-convert
#SBATCH --nodes=1
#SBATCH --partition=RTX4090
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=96G
#SBATCH --output=/home/xshi/projects/VisionPay-Agent/log/%x-%j.out
#SBATCH --error=/home/xshi/projects/VisionPay-Agent/log/%x-%j.err

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT=$(cd "$SCRIPT_DIR/../.." && pwd)

DATA_ROOT=/data0/xshi/datasets/visionpay
RAW_DIR="$DATA_ROOT/raw/hf_rpc"
OUT_DIR="$DATA_ROOT/yolo/vision_pay"
CONVERTER="$SCRIPT_DIR/convert_hf_rpc_to_yolo.py"
BACKEND="$PROJECT/backend"
PY=/home/xshi/miniconda3/envs/kaggle/bin/python

export HF_HOME="$DATA_ROOT/hf_cache"
export HF_DATASETS_CACHE="$DATA_ROOT/hf_cache/datasets"
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

echo "[$(date '+%F %T')] job_id=${SLURM_JOB_ID:-manual} host=$(hostname)"
echo "DATA_ROOT=$DATA_ROOT"
echo "RAW_DIR=$RAW_DIR"
echo "OUT_DIR=$OUT_DIR"
echo "CONVERTER=$CONVERTER"

if [ ! -x "$PY" ]; then
  echo "ERROR: python not found: $PY" >&2
  exit 1
fi
if [ ! -f "$CONVERTER" ]; then
  echo "ERROR: converter not found: $CONVERTER" >&2
  exit 1
fi
if [ ! -d "$RAW_DIR/data" ]; then
  echo "ERROR: raw parquet dir not found: $RAW_DIR/data" >&2
  exit 1
fi

PARQUET_COUNT=$(find "$RAW_DIR/data" -maxdepth 1 -name '*.parquet' | wc -l)
echo "parquet_count=$PARQUET_COUNT"
if [ "$PARQUET_COUNT" -ne 33 ]; then
  echo "ERROR: expected 33 parquet files, got $PARQUET_COUNT" >&2
  exit 1
fi

# Clean only the intended YOLO output directory.
mkdir -p "$DATA_ROOT/yolo"
RESOLVED_OUT=$(realpath -m "$OUT_DIR")
case "$RESOLVED_OUT" in
  "$DATA_ROOT"/yolo/vision_pay)
    if [ -e "$RESOLVED_OUT" ]; then
      echo "removing old output: $RESOLVED_OUT"
      rm -rf -- "$RESOLVED_OUT"
    fi
    ;;
  *)
    echo "ERROR: unsafe output path: $RESOLVED_OUT" >&2
    exit 2
    ;;
esac

echo "[$(date '+%F %T')] start conversion"
"$PY" "$CONVERTER" \
  --source "$RAW_DIR" \
  --output "$OUT_DIR" \
  --clean \
  --progress-every 2000

echo "[$(date '+%F %T')] conversion finished"
echo "output_size=$(du -sh "$OUT_DIR" | awk '{print $1}')"
for split in train val test; do
  imgs=$(find "$OUT_DIR/images/$split" -type f | wc -l)
  lbls=$(find "$OUT_DIR/labels/$split" -type f | wc -l)
  echo "$split images=$imgs labels=$lbls"
done

echo "[$(date '+%F %T')] run dataset verification"
"$PY" "$BACKEND/tools/verify_dataset.py" "$OUT_DIR"

echo "[$(date '+%F %T')] all done"
echo "data_yaml=$OUT_DIR/data.yaml"
