#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$PROJECT/backend"
source .venv/bin/activate
export TMPDIR=/home/xshi/tmp
export YOLO_CONFIG_DIR=/home/xshi/.config/Ultralytics
export PYTHONUNBUFFERED=1

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  alembic upgrade head
fi

exec uvicorn main:app --host 0.0.0.0 --port "${BACKEND_PORT:-8000}"
