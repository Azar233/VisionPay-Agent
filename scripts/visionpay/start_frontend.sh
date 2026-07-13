#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT=$(cd "$SCRIPT_DIR/../.." && pwd)
source /home/xshi/miniconda3/etc/profile.d/conda.sh
conda activate visionpay-node
cd "$PROJECT/frontend"
exec npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT:-5173}"
