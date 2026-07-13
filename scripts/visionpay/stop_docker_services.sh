#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
COMPOSE="$SCRIPT_DIR/docker-compose.cluster.yml"
if ! id -nG | tr ' ' '\n' | grep -qx docker; then
  echo "ERROR: current shell has no docker group permission. Run newgrp docker or re-login before stopping services." >&2
  exit 3
fi
docker compose -f "$COMPOSE" down
