#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import os, socket, sys, urllib.request
try:
    urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read()
except Exception as e:
    print(f'api health failed: {e}', file=sys.stderr)
    sys.exit(1)
# Bridge may be unavailable before first MT5/Python install or manual login; do not fail container health for it.
# Readiness tests validate bridge via API/tests.
PY
