#!/usr/bin/env bash
set -euo pipefail
export HOME=/home/trader
export DISPLAY="${DISPLAY:-:99}"
export WINEPREFIX="${WINEPREFIX:-/config/.wine}"
export WINEARCH="${WINEARCH:-win64}"
export WINEDEBUG="${WINEDEBUG:--all}"
export LIBGL_ALWAYS_SOFTWARE=1
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
MT5_FILE="${MT5_FILE:-/config/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe}"
if [[ ! -f "$MT5_FILE" ]]; then
  echo "MT5 not found: $MT5_FILE" >&2
  exit 1
fi
wine "$MT5_FILE" ${MT5_CMD_OPTIONS:-} >/logs/mt5-terminal-manual.log 2>&1 &
echo "Started MT5. Log: /logs/mt5-terminal-manual.log"
