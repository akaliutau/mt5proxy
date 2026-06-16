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
exec websockify --web=/usr/share/novnc "0.0.0.0:${NOVNC_PORT:-6080}" "127.0.0.1:${VNC_PORT:-5900}"
