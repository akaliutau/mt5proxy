#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "This removes the local Docker container and named volumes mt5_config/mt5_logs for a clean Wine prefix."
echo "Use after changing Wine packages or after a poisoned/broken Wine prefix."
docker compose down -v --remove-orphans
