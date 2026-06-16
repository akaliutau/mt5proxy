#!/usr/bin/env bash
set -euo pipefail
export HOME=/home/trader
export USER=trader
export DISPLAY="${DISPLAY:-:99}"
export WINEPREFIX="${WINEPREFIX:-/config/.wine}"
export WINEARCH="${WINEARCH:-win64}"
export WINEDEBUG="${WINEDEBUG:--all}"
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
export MESA_LOADER_DRIVER_OVERRIDE="${MESA_LOADER_DRIVER_OVERRIDE:-llvmpipe}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-mscoree=d;mshtml=d;winemenubuilder.exe=d}"
export NO_AT_BRIDGE=1
mkdir -p /logs /run/mt5-proxy
for _ in $(seq 1 60); do
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
  echo "ERROR: X display $DISPLAY was not ready for x11vnc" >&2
  exit 1
fi
if [[ -n "${VNC_PASSWORD:-}" ]]; then
  x11vnc -storepasswd "${VNC_PASSWORD}" /run/mt5-proxy/vnc.pass >/dev/null 2>&1
  exec x11vnc -display "$DISPLAY" -forever -shared -rfbauth /run/mt5-proxy/vnc.pass -listen 0.0.0.0 -rfbport "${VNC_PORT:-5900}"
fi
exec x11vnc -display "$DISPLAY" -forever -shared -nopw -listen 0.0.0.0 -rfbport "${VNC_PORT:-5900}"
