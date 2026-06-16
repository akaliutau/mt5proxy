#!/usr/bin/env bash
set -uo pipefail

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

MT5_FILE="${MT5_FILE:-/config/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe}"
PYVENV="${PYVENV:-/opt/mt5-proxy-venv/bin/python}"
BRIDGE_HOST="${MT5LINUX_BIND_HOST:-0.0.0.0}"
BRIDGE_PORT="${MT5LINUX_PORT:-8001}"
WINE_PYTHON_DIR="${WINE_PYTHON_DIR:-$WINEPREFIX/drive_c/Python39}"
WINE_PYTHON_EXE="${WINE_PYTHON_EXE:-$WINE_PYTHON_DIR/python.exe}"
MT5_SETUP_URL="${MT5_SETUP_URL:-https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe}"
WINE_MONO_URL="${WINE_MONO_URL:-https://dl.winehq.org/wine/wine-mono/10.3.0/wine-mono-10.3.0-x86.msi}"
RUN_DIR="${RUN_DIR:-/run/mt5-proxy}"
HEALTH_INTERVAL="${MT5_STACK_HEALTH_INTERVAL:-30}"
BRIDGE_INIT_RETRY_SECONDS="${BRIDGE_INIT_RETRY_SECONDS:-60}"
BRIDGE_INIT_TIMEOUT_SECONDS="${BRIDGE_INIT_TIMEOUT_SECONDS:-120}"
WINE_PYTHON_RETRY_SECONDS="${WINE_PYTHON_RETRY_SECONDS:-300}"
MT5_INSTALL_RETRY_SECONDS="${MT5_INSTALL_RETRY_SECONDS:-600}"
WINESERVER_WAIT_TIMEOUT_SECONDS="${WINESERVER_WAIT_TIMEOUT_SECONDS:-120}"
MT5_INSTALL_TIMEOUT_SECONDS="${MT5_INSTALL_TIMEOUT_SECONDS:-600}"
WINE_PYTHON_INSTALL_TIMEOUT_SECONDS="${WINE_PYTHON_INSTALL_TIMEOUT_SECONDS:-900}"
BRIDGE_PID_FILE="$RUN_DIR/mt5-bridge.pid"
MT5_PID_FILE="$RUN_DIR/mt5-terminal.pid"
LAST_WINE_PYTHON_ATTEMPT=0
LAST_MT5_INSTALL_ATTEMPT=0
LAST_BRIDGE_INIT_ATTEMPT=0

mkdir -p /logs "$RUN_DIR" "$WINEPREFIX"

log() { echo "[$(date -Is)] $*"; }

cleanup() {
  log "Stopping MT5 stack children"
  if [[ -f "$BRIDGE_PID_FILE" ]]; then
    kill "$(cat "$BRIDGE_PID_FILE")" >/dev/null 2>&1 || true
  fi
  if [[ -f "$MT5_PID_FILE" ]]; then
    kill "$(cat "$MT5_PID_FILE")" >/dev/null 2>&1 || true
  fi
  wineserver -k >/dev/null 2>&1 || true
}
trap cleanup TERM INT

should_retry() {
  local last="$1"
  local interval="$2"
  local now
  now="$(date +%s)"
  [[ $((now - last)) -ge "$interval" ]]
}

wait_for_x() {
  for _ in $(seq 1 90); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  log "ERROR: X display $DISPLAY is not ready"
  return 1
}

wine_wait() {
  timeout "$WINESERVER_WAIT_TIMEOUT_SECONDS" wineserver -w >/dev/null 2>&1 || true
}

wine_ok() {
  timeout 60 wine cmd /c echo OK >/tmp/wine-ok.txt 2>/tmp/wine-ok.err && grep -q OK /tmp/wine-ok.txt
}

init_wine() {
  mkdir -p "$WINEPREFIX"
  log "Wine version: $(wine --version 2>/dev/null || echo missing)"
  log "Initializing Wine prefix: $WINEPREFIX"
  timeout 180 wineboot --init >/logs/wineboot.log 2>&1 || true
  wine_wait
  if wine_ok; then
    log "Wine cmd sanity OK"
  else
    log "WARN: wine cmd sanity failed. See /tmp/wine-ok.err. Continuing because GUI may still need first-run setup."
    cat /tmp/wine-ok.err 2>/dev/null || true
  fi
  timeout 60 wine reg add "HKEY_CURRENT_USER\\Software\\Wine" /v Version /t REG_SZ /d "win10" /f >/dev/null 2>&1 || true
}

install_mono() {
  # Avoid the interactive Wine Mono popup. Failure is non-fatal for MT5 startup.
  if [[ -d "$WINEPREFIX/drive_c/windows/mono" ]]; then
    log "Wine Mono appears installed"
    return 0
  fi
  log "Installing Wine Mono non-interactively"
  mkdir -p "$WINEPREFIX/drive_c"
  curl -L --retry 3 --fail -o "$WINEPREFIX/drive_c/wine-mono.msi" "$WINE_MONO_URL" || return 0
  timeout 300 env WINEDLLOVERRIDES="mscoree=d" wine msiexec /i "$WINEPREFIX/drive_c/wine-mono.msi" /qn >/logs/wine-mono-install.log 2>&1 || true
  wine_wait
  rm -f "$WINEPREFIX/drive_c/wine-mono.msi"
}

wine_python_ready() {
  [[ -f "$WINE_PYTHON_EXE" ]] || return 1
  timeout 90 wine "$WINE_PYTHON_EXE" -c "import MetaTrader5, mt5linux, rpyc; print('imports OK')" >/tmp/mt5-import.txt 2>&1
}

ensure_wine_python() {
  if [[ "${WINE_PYTHON_INSTALL_FORCE:-false}" != "true" ]] && wine_python_ready; then
    log "Windows Python and bridge packages are ready"
    return 0
  fi

  if ! should_retry "$LAST_WINE_PYTHON_ATTEMPT" "$WINE_PYTHON_RETRY_SECONDS"; then
    log "Windows Python is not ready; retry is throttled"
    return 1
  fi
  LAST_WINE_PYTHON_ATTEMPT="$(date +%s)"

  log "Ensuring Windows embeddable Python and MT5 bridge packages"
  if timeout "$WINE_PYTHON_INSTALL_TIMEOUT_SECONDS" install_wine_python.sh >>/logs/wine-python-install.log 2>&1; then
    if wine_python_ready; then
      log "Windows Python install/import check passed"
      return 0
    fi
    log "WARN: Windows Python install finished, but import check failed"
    cat /tmp/mt5-import.txt 2>/dev/null || true
    return 1
  fi

  log "WARN: install_wine_python.sh failed or timed out. See /logs/wine-python-install.log"
  tail -100 /logs/wine-python-install.log 2>/dev/null || true
  return 1
}

install_mt5_if_needed() {
  if [[ -f "$MT5_FILE" ]]; then
    log "MT5 already installed: $MT5_FILE"
    return 0
  fi
  if [[ "${MT5_AUTOINSTALL:-true}" != "true" ]]; then
    log "MT5 is not installed and MT5_AUTOINSTALL=false. Use noVNC and run install_mt5_manual.sh."
    return 0
  fi
  if ! should_retry "$LAST_MT5_INSTALL_ATTEMPT" "$MT5_INSTALL_RETRY_SECONDS"; then
    log "MT5 is not installed; installer retry is throttled"
    return 1
  fi
  LAST_MT5_INSTALL_ATTEMPT="$(date +%s)"

  log "Downloading MT5 installer"
  curl -L --retry 3 --fail -o /tmp/mt5setup.exe "$MT5_SETUP_URL" || { log "MT5 download failed"; return 1; }
  log "Running MT5 installer with /auto, bounded by ${MT5_INSTALL_TIMEOUT_SECONDS}s"
  timeout "$MT5_INSTALL_TIMEOUT_SECONDS" wine /tmp/mt5setup.exe /auto >/logs/mt5-install.log 2>&1 || true
  wine_wait
  rm -f /tmp/mt5setup.exe
  if [[ -f "$MT5_FILE" ]]; then
    log "MT5 installed successfully"
    return 0
  fi
  log "WARN: MT5 installer did not create $MT5_FILE. See /logs/mt5-install.log; manual noVNC install may still be required."
  return 1
}

start_mt5() {
  if [[ ! -f "$MT5_FILE" ]]; then
    log "MT5 file not found; cannot start terminal yet"
    return 1
  fi
  if pgrep -f "terminal64.exe" >/dev/null 2>&1; then
    log "MT5 terminal already running"
    return 0
  fi
  log "Starting MT5 terminal"
  # Intentional word splitting of MT5_CMD_OPTIONS preserves the existing script behaviour.
  # shellcheck disable=SC2086
  wine "$MT5_FILE" ${MT5_CMD_OPTIONS:-} >>/logs/mt5-terminal.log 2>&1 &
  echo "$!" >"$MT5_PID_FILE"
  sleep 10
  if pgrep -f "terminal64.exe" >/dev/null 2>&1; then
    log "MT5 terminal is running"
    return 0
  fi
  log "WARN: MT5 terminal was started but is not detected yet"
  return 1
}

bridge_listening() {
  ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:|\\])${BRIDGE_PORT}$"
}

bridge_init_ok() {
  if ! bridge_listening; then
    return 1
  fi
  log "Trying MT5 initialize through mt5linux bridge"
  if timeout "$BRIDGE_INIT_TIMEOUT_SECONDS" "$PYVENV" /app_tools/bridge_init_probe.py >>/logs/bridge-init.log 2>&1; then
    log "Bridge MT5 initialize probe passed"
    return 0
  fi
  log "WARN: Bridge is listening, but MT5 initialize probe failed. See /logs/bridge-init.log"
  tail -80 /logs/bridge-init.log 2>/dev/null || true
  return 1
}

maybe_probe_bridge_init() {
  if ! should_retry "$LAST_BRIDGE_INIT_ATTEMPT" "$BRIDGE_INIT_RETRY_SECONDS"; then
    return 1
  fi
  LAST_BRIDGE_INIT_ATTEMPT="$(date +%s)"
  bridge_init_ok
}

start_bridge() {
  if bridge_listening; then
    log "mt5linux bridge already listening on $BRIDGE_PORT"
    return 0
  fi
  if ! ensure_wine_python; then
    log "WARN: Windows Python is not ready; bridge not started"
    return 1
  fi
  if ! timeout 90 wine "$WINE_PYTHON_EXE" -c "import MetaTrader5, mt5linux, rpyc; print('imports OK')" >/tmp/mt5-import.txt 2>&1; then
    log "WARN: Wine Python cannot import MetaTrader5/mt5linux/rpyc; bridge not started"
    cat /tmp/mt5-import.txt 2>/dev/null || true
    return 1
  fi
  log "Starting Windows-side mt5linux bridge on ${BRIDGE_HOST}:${BRIDGE_PORT}"
  wine "$WINE_PYTHON_EXE" -m mt5linux --host "$BRIDGE_HOST" -p "$BRIDGE_PORT" >>/logs/mt5-bridge.log 2>&1 &
  echo "$!" >"$BRIDGE_PID_FILE"
  for _ in $(seq 1 45); do
    if bridge_listening; then
      log "mt5linux bridge is listening on $BRIDGE_PORT"
      return 0
    fi
    sleep 1
  done
  log "WARN: mt5linux bridge did not start. Check /logs/mt5-bridge.log"
  if [[ -f "$BRIDGE_PID_FILE" ]]; then
    kill "$(cat "$BRIDGE_PID_FILE")" >/dev/null 2>&1 || true
  fi
  tail -100 /logs/mt5-bridge.log 2>/dev/null || true
  return 1
}

main() {
  wait_for_x || true
  init_wine
  install_mono || true

  # Python is intentionally prepared before MT5 installation. If the MT5 installer hangs or requires GUI
  # interaction, the bridge runtime is still ready and no manual install_wine_python.sh step is needed.
  ensure_wine_python || true
  install_mt5_if_needed || true
  start_mt5 || true
  start_bridge || true
  maybe_probe_bridge_init || true

  while true; do
    sleep "$HEALTH_INTERVAL"
    ensure_wine_python || true
    install_mt5_if_needed || true

    if [[ -f "$MT5_FILE" ]] && ! pgrep -f "terminal64.exe" >/dev/null 2>&1; then
      log "MT5 terminal not detected; restarting"
      start_mt5 || true
    fi
    if ! bridge_listening; then
      log "Bridge not detected; restarting"
      start_bridge || true
    else
      maybe_probe_bridge_init || true
    fi
  done
}

main "$@"
