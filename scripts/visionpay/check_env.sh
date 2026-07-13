#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT=$(cd "$SCRIPT_DIR/../.." && pwd)

echo "host=$(hostname) user=$(whoami)"
echo "groups=$(id -nG)"
echo "--- backend ---"
"$PROJECT/backend/.venv/bin/python" --version
"$PROJECT/backend/.venv/bin/python" - <<'PY'
from pathlib import Path
import fastapi, uvicorn, ultralytics, torch
print('fastapi', fastapi.__version__)
print('uvicorn', uvicorn.__version__)
print('ultralytics', ultralytics.__version__)
print('torch', torch.__version__, 'cuda', torch.cuda.is_available())
print('dataset', (Path('/data0/xshi/datasets/visionpay/yolo/vision_pay_sample_2k/data.yaml')).resolve())
PY

echo "--- frontend ---"
source /home/xshi/miniconda3/etc/profile.d/conda.sh
conda activate visionpay-node
node --version
npm --version

echo "--- docker ---"
docker --version || true
docker compose version || true
docker info --format 'server={{.ServerVersion}} root={{.DockerRootDir}}' 2>&1 || true
