#!/usr/bin/env bash
set -euo pipefail
export HOME=/home/trader
export DISPLAY="${DISPLAY:-:99}"
export WINEPREFIX="${WINEPREFIX:-/config/.wine}"
export WINEARCH="${WINEARCH:-win64}"
export WINEDEBUG="${WINEDEBUG:--all}"
export LIBGL_ALWAYS_SOFTWARE=1
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export WINEDLLOVERRIDES="mscoree=d;mshtml=d;winemenubuilder.exe=d"
MT5_SETUP_URL="${MT5_SETUP_URL:-https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe}"

echo "Downloading MT5 installer..."
curl -L --retry 3 -o /tmp/mt5setup.exe "$MT5_SETUP_URL"
echo "Launching MT5 installer. Finish it through noVNC."
wine /tmp/mt5setup.exe
