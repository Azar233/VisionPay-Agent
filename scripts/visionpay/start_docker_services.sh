#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
COMPOSE="$SCRIPT_DIR/docker-compose.cluster.yml"
STATE_DIR=${VISIONPAY_DOCKER_STATE_DIR:-/home/xshi/.local/share/visionpay/docker}

if [ "$(hostname)" = "storage-hdd" ]; then
  echo "ERROR: this is storage-hdd login/storage node. Allocate a cpu/GPU node with salloc/srun before starting Docker." >&2
  exit 2
fi

if ! id -nG | tr ' ' '\n' | grep -qx docker; then
  echo "ERROR: current shell has no docker group permission. Ask admin to authorize, then re-login or run newgrp docker." >&2
  id
  getent group docker || true
  exit 3
fi

mkdir -p "$STATE_DIR/postgres" "$STATE_DIR/redis" "$STATE_DIR/minio"

echo "host=$(hostname)"
echo "compose=$COMPOSE"
echo "state_dir=$STATE_DIR"
docker info --format 'docker_server={{.ServerVersion}} root={{.DockerRootDir}}'
docker compose -f "$COMPOSE" up -d postgres redis minio
docker compose -f "$COMPOSE" ps
