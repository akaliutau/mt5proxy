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

BRIDGE_PORT="${MT5LINUX_PORT:-8001}"
BRIDGE_HOST="${MT5LINUX_BIND_HOST:-0.0.0.0}"
WINE_PYTHON_DIR="${WINE_PYTHON_DIR:-$WINEPREFIX/drive_c/Python39}"
WINE_PYTHON_EXE="${WINE_PYTHON_EXE:-$WINE_PYTHON_DIR/python.exe}"
LOG_FILE="${BRIDGE_LOG_FILE:-/logs/mt5-bridge.log}"

mkdir -p /logs

echo "[$(date -Is)] Resetting original mt5linux bridge on port $BRIDGE_PORT" | tee -a "$LOG_FILE"
pkill -f "python.exe.*mt5linux" || true
pkill -f "Python39.*mt5linux" || true
pkill -f "mt5linux.*$BRIDGE_PORT" || true
lsof -tiTCP:"$BRIDGE_PORT" -sTCP:LISTEN | xargs -r kill -9 || true
sleep 2

if [[ ! -f "$WINE_PYTHON_EXE" ]]; then
  echo "[$(date -Is)] Windows Python missing; running original install_wine_python.sh" | tee -a "$LOG_FILE"
  install_wine_python.sh 2>&1 | tee -a /logs/install-wine-python.log
fi

echo "[$(date -Is)] Wine version: $(wine --version 2>/dev/null || true)" | tee -a "$LOG_FILE"
echo "[$(date -Is)] Python version/import check" | tee -a "$LOG_FILE"
wine "$WINE_PYTHON_EXE" -V 2>&1 | tee -a "$LOG_FILE"
wine "$WINE_PYTHON_EXE" -c "import MetaTrader5, mt5linux, rpyc; print('imports OK')" 2>&1 | tee -a "$LOG_FILE"

echo "[$(date -Is)] Starting original bridge command" | tee -a "$LOG_FILE"
nohup wine "$WINE_PYTHON_EXE" -m mt5linux --host "$BRIDGE_HOST" -p "$BRIDGE_PORT" >>"$LOG_FILE" 2>&1 &

for _ in {1..30}; do
  if ss -tuln | grep -q ":$BRIDGE_PORT "; then
    echo "[$(date -Is)] Bridge listening on $BRIDGE_PORT" | tee -a "$LOG_FILE"
    exit 0
  fi
  sleep 1
done

echo "[$(date -Is)] ERROR: bridge did not listen on $BRIDGE_PORT" | tee -a "$LOG_FILE"
tail -200 "$LOG_FILE" >&2 || true
exit 1
