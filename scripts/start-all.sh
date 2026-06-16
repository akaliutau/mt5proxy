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

log "Starting Xvfb on ${DISPLAY}"
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
Xvfb "$DISPLAY" -screen 0 "${SCREEN_WIDTH:-1280}x${SCREEN_HEIGHT:-900}x${SCREEN_DEPTH:-24}" +extension GLX +render -noreset >/logs/xvfb.log 2>&1 &
sleep 2

log "Starting fluxbox"
fluxbox >/logs/fluxbox.log 2>&1 &

log "Starting x11vnc on ${VNC_PORT:-5900}"
if [[ -n "${VNC_PASSWORD:-}" ]]; then
  x11vnc -storepasswd "${VNC_PASSWORD}" /run/mt5-proxy/vnc.pass >/dev/null 2>&1
  x11vnc -display "$DISPLAY" -forever -shared -rfbauth /run/mt5-proxy/vnc.pass -listen 0.0.0.0 -rfbport "${VNC_PORT:-5900}" >/logs/x11vnc.log 2>&1 &
else
  x11vnc -display "$DISPLAY" -forever -shared -nopw -listen 0.0.0.0 -rfbport "${VNC_PORT:-5900}" >/logs/x11vnc.log 2>&1 &
fi

log "Starting noVNC on ${NOVNC_PORT:-6080}"
websockify --web=/usr/share/novnc "0.0.0.0:${NOVNC_PORT:-6080}" "127.0.0.1:${VNC_PORT:-5900}" >/logs/novnc.log 2>&1 &

log "Starting FastAPI proxy on 8000"
/opt/mt5-proxy-venv/bin/uvicorn mt5_proxy.main:app --host 0.0.0.0 --port 8000 >/logs/api.log 2>&1 &

log "Starting MT5 stack supervisor"
/usr/local/bin/mt5-stack.sh >/logs/mt5-stack.log 2>&1 &

log "Startup complete. noVNC: http://127.0.0.1:3000/vnc.html ; API: http://127.0.0.1:8000/health"

# Keep container alive. If any core child exits early, continue logging; Docker restart handles fatal entrypoint exits.
while true; do
  sleep 30
  if ! pgrep -f "uvicorn mt5_proxy.main:app" >/dev/null; then
    log "API process is not running; restarting"
    /opt/mt5-proxy-venv/bin/uvicorn mt5_proxy.main:app --host 0.0.0.0 --port 8000 >>/logs/api.log 2>&1 &
  fi
  if ! pgrep -f "websockify.*${NOVNC_PORT:-6080}" >/dev/null; then
    log "websockify is not running; restarting"
    websockify --web=/usr/share/novnc "0.0.0.0:${NOVNC_PORT:-6080}" "127.0.0.1:${VNC_PORT:-5900}" >>/logs/novnc.log 2>&1 &
  fi
done
