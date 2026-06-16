#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.example "$ENV_FILE"
  echo "Created $ENV_FILE from .env.example. Edit it for MT5 credentials, API key, and VNC password if needed."
fi

BUILD_FLAG="--build"
if [[ "${1:-}" == "--no-build" ]]; then
  BUILD_FLAG=""
  shift
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d $BUILD_FLAG --remove-orphans "$@"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps

echo
echo "API:   http://127.0.0.1:${API_HOST_PORT:-8000}/health"
echo "noVNC: http://127.0.0.1:${NOVNC_HOST_PORT:-3000}/vnc.html"
echo "Logs:  docker compose --env-file $ENV_FILE -f $COMPOSE_FILE logs -f mt5proxy"
