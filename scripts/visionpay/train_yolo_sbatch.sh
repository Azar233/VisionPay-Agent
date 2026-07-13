#!/usr/bin/env bash
#SBATCH --job-name=sx_train
#SBATCH --partition=RTX4090
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:8
#SBATCH --cpus-per-task=64
#SBATCH --mem=400G
#SBATCH --time=2-00:00:00
#SBATCH --output=/home/xshi/projects/VisionPay-Agent/log/%j_%x.out
#SBATCH --error=/home/xshi/projects/VisionPay-Agent/log/%j_%x.err

set -euo pipefail

PROJECT=/home/xshi/projects/VisionPay-Agent
BACKEND=$PROJECT/backend
DATASET=${DATASET:-/data0/xshi/datasets/visionpay/yolo/vision_pay_mixed_train4800_val1200}
DATA_YAML=${DATA_YAML:-$DATASET/data.yaml}
SCENE_ID=${SCENE_ID:-1}
MODEL_WEIGHT=${MODEL_WEIGHT:-yolo11x.pt}
MODEL_NAME=${MODEL_NAME:-yolov11x}
EPOCHS=${EPOCHS:-50}
BATCH=${BATCH:-128}
IMGSZ=${IMGSZ:-640}
DEVICE=${DEVICE:-0,1,2,3,4,5,6,7}
OPTIMIZER=${OPTIMIZER:-SGD}
LR0=${LR0:-0.01}
RUN_NAME=${RUN_NAME:-task_sbatch_mixed_${MODEL_NAME}_${SLURM_JOB_ID:-manual}}
RUN_DIR=$BACKEND/runs/train/$RUN_NAME
LOG_PATH=$PROJECT/log/${SLURM_JOB_ID:-manual}_${RUN_NAME}.train.log

mkdir -p "$PROJECT/log" /home/xshi/tmp /home/xshi/.config/Ultralytics
exec > >(tee -a "$LOG_PATH") 2>&1

cd "$BACKEND"
source .venv/bin/activate
export TMPDIR=/home/xshi/tmp
export YOLO_CONFIG_DIR=/home/xshi/.config/Ultralytics
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-4}

echo "host=$(hostname)"
echo "job_id=${SLURM_JOB_ID:-none}"
echo "run_name=$RUN_NAME"
echo "run_dir=$RUN_DIR"
echo "data_yaml=$DATA_YAML"
echo "model_weight=$MODEL_WEIGHT model_name=$MODEL_NAME epochs=$EPOCHS batch=$BATCH imgsz=$IMGSZ device=$DEVICE optimizer=$OPTIMIZER lr0=$LR0"

python -u - <<PY
from ultralytics import YOLO
model = YOLO("$MODEL_WEIGHT")
model.train(
    data="$DATA_YAML",
    epochs=int("$EPOCHS"),
    imgsz=int("$IMGSZ"),
    batch=int("$BATCH"),
    device="$DEVICE",
    optimizer="$OPTIMIZER",
    lr0=float("$LR0"),
    project="$BACKEND/runs/train",
    name="$RUN_NAME",
    exist_ok=True,
    save=True,
    plots=True,
    verbose=True,
    degrees=5,
    translate=0.05,
    scale=0.25,
    flipud=0.0,
    fliplr=0.5,
    mosaic=0.3,
    mixup=0.0,
    close_mosaic=10,
)
PY

if [ -d "$RUN_DIR" ]; then
  cp "$LOG_PATH" "$RUN_DIR/train.log"
fi

cat > "$RUN_DIR/import_payload.json" <<JSON
{
  "scene_id": $SCENE_ID,
  "run_dir": "$RUN_DIR",
  "task_uuid": "${RUN_NAME#task_}",
  "model_name": "$MODEL_NAME",
  "dataset_path": "$DATASET",
  "data_yaml": "$DATA_YAML",
  "log_path": "$LOG_PATH"
}
JSON

echo "training finished"
echo "import_payload=$RUN_DIR/import_payload.json"
echo "frontend import run_dir=$RUN_DIR"
