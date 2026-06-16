#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
export SCREEN_WIDTH="${SCREEN_WIDTH:-1280}"
export SCREEN_HEIGHT="${SCREEN_HEIGHT:-900}"
export SCREEN_DEPTH="${SCREEN_DEPTH:-24}"

mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix || true
DISPLAY_NUM="${DISPLAY#:}"
DISPLAY_NUM="${DISPLAY_NUM%%.*}"
rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}" 2>/dev/null || true

exec Xvfb "$DISPLAY" -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" +extension GLX +render -noreset
