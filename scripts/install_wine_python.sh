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

NUMPY_VERSION="${WINDOWS_NUMPY_VERSION:-1.26.4}"
MT5_PKG_VERSION="${WINDOWS_METATRADER5_VERSION:-5.0.36}"
MT5LINUX_VERSION="${WINDOWS_MT5LINUX_VERSION:-1.0.3}"
RPYC_VERSION="${WINDOWS_RPYC_VERSION:-6.0.2}"

log() { echo "[$(date -Is)] $*"; }

ensure_x() {
  if ! pgrep -x Xvfb >/dev/null 2>&1; then
    Xvfb "$DISPLAY" -screen 0 1280x900x24 +extension GLX +render -noreset >/tmp/xvfb-install-python.log 2>&1 &
    sleep 2
  fi
}

ensure_wine_prefix() {
  mkdir -p "$WINEPREFIX"
  wineboot --init >/tmp/wineboot-install-python.log 2>&1 || true
  wineserver -w || true
}

install_embedded_python() {
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
  python3 - "$pth" <<'PY'
from pathlib import Path
import sys
pth = Path(sys.argv[1])
lines = pth.read_text().splitlines()
out = []
seen_site_packages = False
seen_import_site = False
for line in lines:
    stripped = line.strip()
    if stripped == "Lib\\site-packages" or stripped == "Lib/site-packages":
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
PY
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
  wine "$WINE_PYTHON_EXE" -V

  log "Windows-side import check"
  wine "$WINE_PYTHON_EXE" -c "import sys; print(sys.version); import numpy; print('numpy', numpy.__version__); import MetaTrader5; print('MetaTrader5 OK'); import mt5linux; print('mt5linux OK'); import rpyc; print('rpyc OK')"
}

main() {
  ensure_x
  ensure_wine_prefix
  install_embedded_python
  configure_embedded_python_paths
  download_wheels
  extract_wheels_to_embedded_python
  wine_python_test
  log "WINE_PYTHON_READY=$WINE_PYTHON_EXE"
}

main "$@"
