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
FORCE_RESTART_BRIDGE="${FORCE_RESTART_BRIDGE:-false}"

mkdir -p /logs /run/mt5-proxy

kill_bridge_listeners() {
  local pids
  pids="$(lsof -tiTCP:"$BRIDGE_PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true)"
  if [[ -n "$pids" ]]; then
    echo "Killing process(es) listening on ${BRIDGE_PORT}: ${pids}"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 2
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
  pkill -f "python.exe.*mt5linux.*${BRIDGE_PORT}" 2>/dev/null || true
  pkill -f "Python39.*mt5linux.*${BRIDGE_PORT}" 2>/dev/null || true
}

if [[ ! -f "$WINE_PYTHON_EXE" ]]; then
  echo "ERROR: Windows Python is missing: $WINE_PYTHON_EXE" >&2
  echo "Run inside container as trader: install_wine_python.sh" >&2
  exit 1
fi

if ss -tuln | grep -q ":$BRIDGE_PORT "; then
  if [[ "$FORCE_RESTART_BRIDGE" == "true" ]]; then
    kill_bridge_listeners
  else
    echo "mt5linux bridge already listening on $BRIDGE_PORT"
    exit 0
  fi
fi

echo "Checking Windows-side imports..."
timeout 60 wine "$WINE_PYTHON_EXE" -c "import MetaTrader5, mt5linux, rpyc; print('Windows-side imports OK')"

echo "Starting Windows-side mt5linux RPyC server on ${BRIDGE_HOST}:${BRIDGE_PORT}"
echo "Command: wine $WINE_PYTHON_EXE -u -m mt5linux --host $BRIDGE_HOST -p $BRIDGE_PORT"
exec wine "$WINE_PYTHON_EXE" -u -m mt5linux --host "$BRIDGE_HOST" -p "$BRIDGE_PORT"
