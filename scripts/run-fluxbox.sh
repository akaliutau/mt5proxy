#!/usr/bin/env bash
set -euo pipefail
export DISPLAY="${DISPLAY:-:99}"

for _ in $(seq 1 60); do
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    exec fluxbox
  fi
  sleep 1
done

echo "ERROR: X display $DISPLAY is not ready for fluxbox" >&2
exit 1
