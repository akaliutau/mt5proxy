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
WINE_PYTHON_INSTALL_TIMEOUT_SECONDS="${WINE_PYTHON_INSTALL_TIMEOUT_SECONDS:-900}"
RUN_DIR="${RUN_DIR:-/run/mt5-proxy}"
IMPORT_LOG="/tmp/mt5-start-bridge-import.log"
LOCK_FILE="$RUN_DIR/start-bridge.lock"

mkdir -p /logs "$RUN_DIR"

bridge_listening() {
  ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:|\])${BRIDGE_PORT}$"
}

wine_import_check() {
  [[ -f "$WINE_PYTHON_EXE" ]] || return 1
  timeout 90 wine "$WINE_PYTHON_EXE" -c "import sys; print(sys.version); import MetaTrader5, mt5linux, rpyc; print('Windows-side imports OK')" >"$IMPORT_LOG" 2>&1
}

ensure_wine_python() {
  echo "Wine version: $(wine --version 2>/dev/null || echo missing)"
  if wine_import_check; then
    cat "$IMPORT_LOG"
    return 0
  fi

  echo "Windows Python/bridge imports are not ready. Running install_wine_python.sh automatically..." >&2
  if [[ -s "$IMPORT_LOG" ]]; then
    echo "Previous import failure:" >&2
    cat "$IMPORT_LOG" >&2 || true
  fi

  timeout "$WINE_PYTHON_INSTALL_TIMEOUT_SECONDS" install_wine_python.sh

  echo "Rechecking Windows-side imports..."
  if wine_import_check; then
    cat "$IMPORT_LOG"
    return 0
  fi

  echo "ERROR: Windows Python exists but cannot import MetaTrader5/mt5linux/rpyc." >&2
  echo "This usually means the Wine runtime/prefix is still broken. If you changed Wine packages, reset the persisted /config volume and rebuild." >&2
  echo "Import log:" >&2
  cat "$IMPORT_LOG" >&2 || true
  return 1
}

if bridge_listening; then
  echo "mt5linux bridge already listening on $BRIDGE_PORT"
  exit 0
fi

# Prevent manual start_bridge.sh and the supervisor stack from installing/running the bridge at the same time.
exec 9>"$LOCK_FILE"
flock 9

if bridge_listening; then
  echo "mt5linux bridge already listening on $BRIDGE_PORT"
  exit 0
fi

ensure_wine_python

echo "Starting Windows-side mt5linux RPyC server on ${BRIDGE_HOST}:${BRIDGE_PORT}"
echo "Command: wine $WINE_PYTHON_EXE -m mt5linux --host $BRIDGE_HOST -p $BRIDGE_PORT"
exec wine "$WINE_PYTHON_EXE" -m mt5linux --host "$BRIDGE_HOST" -p "$BRIDGE_PORT"
