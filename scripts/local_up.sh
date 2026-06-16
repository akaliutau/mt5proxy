#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Edit it before enabling live/demo trading credentials."
fi

docker compose build
docker compose up -d --remove-orphans
docker compose ps

echo
echo "API:   http://127.0.0.1:8000/health"
echo "noVNC: http://127.0.0.1:3000/vnc.html"
echo "Logs:  docker compose logs -f mt5proxy"
