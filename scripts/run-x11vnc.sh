#!/usr/bin/env bash
set -euo pipefail
export DISPLAY="${DISPLAY:-:99}"
export VNC_PORT="${VNC_PORT:-5900}"

for _ in $(seq 1 60); do
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

mkdir -p /run/mt5-proxy
if [[ -n "${VNC_PASSWORD:-}" ]]; then
  x11vnc -storepasswd "${VNC_PASSWORD}" /run/mt5-proxy/vnc.pass >/dev/null 2>&1
  exec x11vnc -display "$DISPLAY" -forever -shared -rfbauth /run/mt5-proxy/vnc.pass -listen 0.0.0.0 -rfbport "$VNC_PORT"
fi

exec x11vnc -display "$DISPLAY" -forever -shared -nopw -listen 0.0.0.0 -rfbport "$VNC_PORT"
