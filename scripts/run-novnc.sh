#!/usr/bin/env bash
set -euo pipefail
export VNC_PORT="${VNC_PORT:-5900}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"

for _ in $(seq 1 60); do
  if ss -tuln | grep -q ":${VNC_PORT} "; then
    exec websockify --web=/usr/share/novnc "0.0.0.0:${NOVNC_PORT}" "127.0.0.1:${VNC_PORT}"
  fi
  sleep 1
done

echo "ERROR: VNC port ${VNC_PORT} is not ready for noVNC" >&2
exit 1
