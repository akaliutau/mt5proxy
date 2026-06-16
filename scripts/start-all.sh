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

mkdir -p /logs /config /run/mt5-proxy "$WINEPREFIX"

echo "[$(date -Is)] Starting supervised MT5 proxy stack" | tee -a /logs/entrypoint.log
echo "[$(date -Is)] noVNC: http://127.0.0.1:3000/vnc.html ; API: http://127.0.0.1:8000/health" | tee -a /logs/entrypoint.log

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/mt5proxy.conf
