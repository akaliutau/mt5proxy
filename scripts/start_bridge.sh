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
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

BRIDGE_HOST="${MT5LINUX_BIND_HOST:-0.0.0.0}"
BRIDGE_PORT="${MT5LINUX_PORT:-8001}"
WINE_PYTHON_DIR="${WINE_PYTHON_DIR:-$WINEPREFIX/drive_c/Python39}"
WINE_PYTHON_EXE="${WINE_PYTHON_EXE:-$WINE_PYTHON_DIR/python.exe}"
LOG_FILE="${BRIDGE_LOG_FILE:-/logs/mt5-bridge.log}"

mkdir -p /logs

if [[ ! -f "$WINE_PYTHON_EXE" ]]; then
  echo "ERROR: Windows Python is missing: $WINE_PYTHON_EXE" >&2
  echo "Run: gosu trader bash -lc 'install_wine_python.sh'" >&2
  exit 1
fi

if ss -tuln | grep -q ":$BRIDGE_PORT "; then
  echo "mt5linux bridge already listening on $BRIDGE_PORT"
  exit 0
fi

echo "Checking Windows-side imports..."
wine "$WINE_PYTHON_EXE" -c "import MetaTrader5, mt5linux, rpyc; print('Windows-side imports OK')"

echo "Starting Windows-side mt5linux RPyC server on ${BRIDGE_HOST}:${BRIDGE_PORT}"
echo "Command: wine $WINE_PYTHON_EXE -m mt5linux --host $BRIDGE_HOST -p $BRIDGE_PORT"
exec wine "$WINE_PYTHON_EXE" -m mt5linux --host "$BRIDGE_HOST" -p "$BRIDGE_PORT"
