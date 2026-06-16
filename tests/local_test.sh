#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
API_KEY="${API_KEY:-dev-api-key}"
SYMBOL="${MT5_TEST_SYMBOL:-EURUSD}"
python3 tests/wait_for_service.py --base-url "$BASE_URL" --api-key "$API_KEY" --timeout 300
python3 -m venv .venv-test
. .venv-test/bin/activate
pip install -q requests
python tests/external_test_all_ops.py --base-url "$BASE_URL" --api-key "$API_KEY" --symbol "$SYMBOL" "$@"
