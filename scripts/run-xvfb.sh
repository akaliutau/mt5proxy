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
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
exec Xvfb "$DISPLAY" -screen 0 "${SCREEN_WIDTH:-1280}x${SCREEN_HEIGHT:-900}x${SCREEN_DEPTH:-24}" +extension GLX +render -noreset
