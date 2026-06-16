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

log() { echo "[$(date -Is)] $*" | tee -a /logs/entrypoint.log; }

cleanup() {
  log "Stopping services..."
  pkill -TERM -P $$ 2>/dev/null || true
  wineserver -k 2>/dev/null || true
}
trap cleanup TERM INT

start_xvfb() {
  if pgrep -x Xvfb >/dev/null 2>&1 && xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    return 0
  fi
  log "Starting Xvfb on ${DISPLAY}"
  rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
  Xvfb "$DISPLAY" -screen 0 "${SCREEN_WIDTH:-1280}x${SCREEN_HEIGHT:-900}x${SCREEN_DEPTH:-24}" +extension GLX +render -noreset >>/logs/xvfb.log 2>&1 &
}

start_fluxbox() {
  if pgrep -x fluxbox >/dev/null 2>&1; then return 0; fi
  log "Starting fluxbox"
  fluxbox >>/logs/fluxbox.log 2>&1 &
}

start_x11vnc() {
  if pgrep -f "x11vnc.*${VNC_PORT:-5900}" >/dev/null 2>&1; then return 0; fi
  log "Starting x11vnc on ${VNC_PORT:-5900}"
  if [[ -n "${VNC_PASSWORD:-}" ]]; then
    x11vnc -storepasswd "${VNC_PASSWORD}" /run/mt5-proxy/vnc.pass >/dev/null 2>&1
    x11vnc -display "$DISPLAY" -forever -shared -rfbauth /run/mt5-proxy/vnc.pass -listen 0.0.0.0 -rfbport "${VNC_PORT:-5900}" >>/logs/x11vnc.log 2>&1 &
  else
    x11vnc -display "$DISPLAY" -forever -shared -nopw -listen 0.0.0.0 -rfbport "${VNC_PORT:-5900}" >>/logs/x11vnc.log 2>&1 &
  fi
}

start_novnc() {
  if pgrep -f "websockify.*${NOVNC_PORT:-6080}" >/dev/null 2>&1; then return 0; fi
  log "Starting noVNC on ${NOVNC_PORT:-6080}"
  websockify --web=/usr/share/novnc "0.0.0.0:${NOVNC_PORT:-6080}" "127.0.0.1:${VNC_PORT:-5900}" >>/logs/novnc.log 2>&1 &
}

start_api() {
  if pgrep -f "uvicorn mt5_proxy.main:app" >/dev/null 2>&1; then return 0; fi
  log "Starting FastAPI proxy on 8000"
  cd /app
  /opt/mt5-proxy-venv/bin/uvicorn mt5_proxy.main:app --host 0.0.0.0 --port 8000 >>/logs/api.log 2>&1 &
}

start_mt5_stack() {
  if pgrep -f "/usr/local/bin/mt5-stack.sh|mt5-stack.sh" >/dev/null 2>&1; then return 0; fi
  log "Starting original MT5 stack supervisor"
  /usr/local/bin/mt5-stack.sh >>/logs/mt5-stack.log 2>&1 &
}

start_xvfb
sleep 2
start_fluxbox
start_x11vnc
start_novnc
start_api
start_mt5_stack

log "Startup complete. noVNC: http://127.0.0.1:3000/vnc.html ; API: http://127.0.0.1:8000/health"

while true; do
  sleep "${WATCHDOG_INTERVAL:-20}"
  start_xvfb || true
  start_fluxbox || true
  start_x11vnc || true
  start_novnc || true
  start_api || true
  start_mt5_stack || true

  # Keep the original bridge lifecycle inside mt5-stack.sh. This only nudges
  # the original stack if the stack process itself died.
  if ! pgrep -f "/usr/local/bin/mt5-stack.sh|mt5-stack.sh" >/dev/null 2>&1; then
    log "MT5 stack process is not running; restarting"
    start_mt5_stack || true
  fi
done
