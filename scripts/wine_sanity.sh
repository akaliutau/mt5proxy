#!/usr/bin/env bash
set -u
export HOME=/home/trader
export DISPLAY="${DISPLAY:-:99}"
export WINEPREFIX="${WINEPREFIX:-/config/.wine}"
export WINEARCH="${WINEARCH:-win64}"
export WINEDEBUG="${WINEDEBUG:--all}"
export LIBGL_ALWAYS_SOFTWARE=1
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-mscoree=d;mshtml=d;winemenubuilder.exe=d}"

echo "== env =="
echo "DISPLAY=$DISPLAY"
echo "WINEPREFIX=$WINEPREFIX"
echo

echo "== X =="
xdpyinfo -display "$DISPLAY" >/dev/null && echo "X OK" || echo "X FAILED"
echo

echo "== Wine version =="
wine --version || exit 1
echo

echo "== Wineboot =="
wineboot --init || true
wineserver -w || true
echo

echo "== Wine cmd =="
wine cmd /c ver || exit 2
wine cmd /c echo OK || exit 3

echo "WINE_SANITY_PASSED"
