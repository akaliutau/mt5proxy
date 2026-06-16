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

# We intentionally do NOT use get-pip.py here.
# In this Wine/Docker setup, get-pip.py can crash with:
#   Fatal Python error: init_sys_streams / OSError: [WinError 6] Invalid handle
# Instead, we install the Windows packages by downloading wheels with Linux pip
# and extracting them directly into the Windows embeddable Python site-packages.
PYTHON_EMBED_URL="${PYTHON_EMBED_URL:-https://www.python.org/ftp/python/3.9.13/python-3.9.13-embed-amd64.zip}"
WINE_PYTHON_DIR="${WINE_PYTHON_DIR:-$WINEPREFIX/drive_c/Python39}"
WINE_PYTHON_EXE="${WINE_PYTHON_EXE:-$WINE_PYTHON_DIR/python.exe}"
WINE_SITE_PACKAGES="${WINE_SITE_PACKAGES:-$WINE_PYTHON_DIR/Lib/site-packages}"
LINUX_PYTHON="${LINUX_PYTHON:-/opt/mt5-proxy-venv/bin/python}"
WHEEL_DIR="${WHEEL_DIR:-/tmp/mt5-windows-wheels}"
RUN_DIR="${RUN_DIR:-/run/mt5-proxy}"
LOCK_DIR="${WINE_PYTHON_LOCK_DIR:-$RUN_DIR/install-wine-python.lock}"

NUMPY_VERSION="${WINDOWS_NUMPY_VERSION:-1.26.4}"
MT5_PKG_VERSION="${WINDOWS_METATRADER5_VERSION:-5.0.36}"
MT5LINUX_VERSION="${WINDOWS_MT5LINUX_VERSION:-1.0.3}"
RPYC_VERSION="${WINDOWS_RPYC_VERSION:-6.0.2}"
WINESERVER_WAIT_TIMEOUT_SECONDS="${WINESERVER_WAIT_TIMEOUT_SECONDS:-120}"

log() { echo "[$(date -Is)] $*"; }

cleanup_lock() {
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
}

acquire_lock() {
  mkdir -p "$(dirname "$LOCK_DIR")"
  for _ in $(seq 1 120); do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      trap cleanup_lock EXIT
      return 0
    fi
    log "Another install_wine_python.sh is running; waiting..."
    sleep 1
  done
  log "ERROR: timed out waiting for $LOCK_DIR"
  return 1
}

ensure_x() {
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    return 0
  fi
  if ! pgrep -x Xvfb >/dev/null 2>&1; then
    Xvfb "$DISPLAY" -screen 0 1280x900x24 +extension GLX +render -noreset >/tmp/xvfb-install-python.log 2>&1 &
  fi
  for _ in $(seq 1 30); do
    xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 && return 0
    sleep 1
  done
  log "WARN: X display $DISPLAY is not ready; continuing because Wine may still initialize headlessly"
}

ensure_wine_prefix() {
  mkdir -p "$WINEPREFIX"
  timeout 180 wineboot --init >/tmp/wineboot-install-python.log 2>&1 || true
  timeout "$WINESERVER_WAIT_TIMEOUT_SECONDS" wineserver -w >/dev/null 2>&1 || true
  wine reg add "HKEY_CURRENT_USER\\Software\\Wine" /v Version /t REG_SZ /d "win10" /f >/dev/null 2>&1 || true
}

wine_python_ready() {
  [[ -f "$WINE_PYTHON_EXE" ]] || return 1
  timeout 90 wine "$WINE_PYTHON_EXE" -c "import sys; import numpy; import MetaTrader5; import mt5linux; import rpyc; print('WINE_PYTHON_READY', sys.version)" >/tmp/wine-python-ready.txt 2>&1
}

install_embedded_python() {
  if [[ "${WINE_PYTHON_RESET:-false}" == "true" ]]; then
    log "WINE_PYTHON_RESET=true; removing $WINE_PYTHON_DIR"
    rm -rf "$WINE_PYTHON_DIR"
  fi
  if [[ -f "$WINE_PYTHON_EXE" ]]; then
    return 0
  fi

  log "Installing Windows Python embeddable distribution into $WINE_PYTHON_DIR"
  rm -rf "$WINE_PYTHON_DIR"
  mkdir -p "$WINE_PYTHON_DIR"
  curl -L --retry 3 --fail -o /tmp/python-embed.zip "$PYTHON_EMBED_URL"
  unzip -q -o /tmp/python-embed.zip -d "$WINE_PYTHON_DIR"
  rm -f /tmp/python-embed.zip
}

configure_embedded_python_paths() {
  mkdir -p "$WINE_SITE_PACKAGES"

  local pth
  pth="$(ls "$WINE_PYTHON_DIR"/python*._pth 2>/dev/null | head -n 1 || true)"
  if [[ -z "$pth" ]]; then
    log "ERROR: cannot find python*._pth in $WINE_PYTHON_DIR"
    exit 1
  fi

  # The embeddable Python distro uses a restrictive ._pth file. Packages are
  # not importable until Lib/site-packages is explicitly listed and import site
  # is enabled.
  python3 - "$pth" <<'PYTHONPATCH'
from pathlib import Path
import sys
pth = Path(sys.argv[1])
lines = pth.read_text().splitlines()
out = []
seen_site_packages = False
seen_import_site = False
for line in lines:
    stripped = line.strip()
    if stripped in {"Lib\\site-packages", "Lib/site-packages"}:
        seen_site_packages = True
    if stripped == "import site":
        seen_import_site = True
    if stripped == "#import site":
        if not seen_site_packages:
            out.append("Lib\\site-packages")
            seen_site_packages = True
        out.append("import site")
        seen_import_site = True
        continue
    out.append(line)
if not seen_site_packages:
    out.append("Lib\\site-packages")
if not seen_import_site:
    out.append("import site")
pth.write_text("\n".join(out) + "\n")
PYTHONPATCH
}

download_wheels() {
  rm -rf "$WHEEL_DIR"
  mkdir -p "$WHEEL_DIR"

  log "Downloading Windows wheels into $WHEEL_DIR"
  "$LINUX_PYTHON" -m pip download --no-cache-dir --only-binary=:all: \
    --platform win_amd64 --implementation cp --python-version 39 \
    --abi cp39 --abi abi3 --abi none --no-deps \
    -d "$WHEEL_DIR" \
    "numpy==$NUMPY_VERSION" "MetaTrader5==$MT5_PKG_VERSION"

  log "Building/downloading pure-Python wheels"
  "$LINUX_PYTHON" -m pip wheel --no-cache-dir --no-deps -w "$WHEEL_DIR" \
    "mt5linux==$MT5LINUX_VERSION" \
    "rpyc==$RPYC_VERSION" \
    "plumbum>=1.8,<2" \
    "python-dateutil>=2.8,<3" \
    "six>=1.16,<2"
}

extract_wheels_to_embedded_python() {
  log "Extracting wheels into $WINE_SITE_PACKAGES"
  mkdir -p "$WINE_SITE_PACKAGES"
  # Keep the embeddable stdlib intact, but replace bridge-related packages so
  # a failed/partial previous installation cannot poison future starts.
  rm -rf \
    "$WINE_SITE_PACKAGES"/MetaTrader5* \
    "$WINE_SITE_PACKAGES"/mt5linux* \
    "$WINE_SITE_PACKAGES"/rpyc* \
    "$WINE_SITE_PACKAGES"/plumbum* \
    "$WINE_SITE_PACKAGES"/numpy \
    "$WINE_SITE_PACKAGES"/numpy-* \
    "$WINE_SITE_PACKAGES"/dateutil \
    "$WINE_SITE_PACKAGES"/python_dateutil* \
    "$WINE_SITE_PACKAGES"/six.py \
    "$WINE_SITE_PACKAGES"/six-* 2>/dev/null || true

  shopt -s nullglob
  local wheel
  for wheel in "$WHEEL_DIR"/*.whl; do
    echo "  -> $(basename "$wheel")"
    unzip -q -o "$wheel" -d "$WINE_SITE_PACKAGES"
  done
  shopt -u nullglob
}

wine_python_test() {
  log "Windows Python version"
  timeout 90 wine "$WINE_PYTHON_EXE" -V

  log "Windows-side import check"
  timeout 90 wine "$WINE_PYTHON_EXE" -c "import sys; print(sys.version); import numpy; print('numpy', numpy.__version__); import MetaTrader5; print('MetaTrader5 OK'); import mt5linux; print('mt5linux OK'); import rpyc; print('rpyc OK')"
}

main() {
  acquire_lock
  ensure_x
  ensure_wine_prefix

  if [[ "${WINE_PYTHON_INSTALL_FORCE:-false}" != "true" ]] && wine_python_ready; then
    cat /tmp/wine-python-ready.txt 2>/dev/null || true
    log "WINE_PYTHON_READY=$WINE_PYTHON_EXE"
    return 0
  fi

  install_embedded_python
  configure_embedded_python_paths
  download_wheels
  extract_wheels_to_embedded_python
  wine_python_test
  log "WINE_PYTHON_READY=$WINE_PYTHON_EXE"
}

main "$@"
