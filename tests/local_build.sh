#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="${ENV_FILE:-.env}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.example "$ENV_FILE"
  echo "Created $ENV_FILE from .env.example. Edit it if needed, then rerun this command."
fi
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build "$@"
