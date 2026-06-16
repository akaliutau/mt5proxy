#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

REMOVE_VOLUMES=false
REMOVE_IMAGES=false
KILL_FIRST=false

usage() {
  cat <<'EOF'
Usage:
  ./scripts/local_down.sh [options]

Options:
  --volumes     Also remove Docker volumes. WARNING: deletes persisted MT5/Wine config.
  --images      Also remove locally built image.
  --kill        Force-kill the container before compose down.
  -h, --help    Show this help.

Examples:
  ./scripts/local_down.sh
  ./scripts/local_down.sh --kill
  ./scripts/local_down.sh --volumes
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --volumes)
      REMOVE_VOLUMES=true
      shift
      ;;
    --images)
      REMOVE_IMAGES=true
      shift
      ;;
    --kill)
      KILL_FIRST=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

echo "Stopping MT5 proxy local stack..."

if [[ "${KILL_FIRST}" == "true" ]]; then
  echo "Force-killing container if it exists..."
  docker rm -f mt5-proxy-scratch >/dev/null 2>&1 || true
fi

DOWN_ARGS=(down --remove-orphans)

if [[ "${REMOVE_VOLUMES}" == "true" ]]; then
  echo "WARNING: removing volumes. This deletes persisted /config and /logs data."
  DOWN_ARGS+=(-v)
fi

if [[ "${REMOVE_IMAGES}" == "true" ]]; then
  DOWN_ARGS+=(--rmi local)
fi

docker compose "${DOWN_ARGS[@]}"

echo
echo "Stack stopped."

if [[ "${REMOVE_VOLUMES}" != "true" ]]; then
  echo "Volumes were preserved."
  echo "Use ./scripts/local_down.sh --volumes to remove persisted MT5/Wine config."
fi
