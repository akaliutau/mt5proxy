#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

API_HOST_PORT="${API_HOST_PORT:-8000}"
API_KEY="${API_KEY:-dev-api-key}"
MT5_TEST_SYMBOL="${MT5_TEST_SYMBOL:-EURUSD}"
MT5_TEST_VOLUME="${MT5_TEST_VOLUME:-0.01}"
LOCAL_TEST_TIMEOUT="${LOCAL_TEST_TIMEOUT:-900}"
BASE_URL="${BASE_URL:-http://127.0.0.1:${API_HOST_PORT}}"
VENV="${LOCAL_TEST_VENV:-.venv-tests}"
PLACE_TRADES=false
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --place-trades)
      PLACE_TRADES=true
      EXTRA_ARGS+=("--place-trades")
      ;;
    *)
      EXTRA_ARGS+=("$1")
      ;;
  esac
  shift
done

python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet requests

if ! python tests/wait_for_service.py --base-url "$BASE_URL" --api-key "$API_KEY" --timeout "$LOCAL_TEST_TIMEOUT" --deep-ready; then
  echo
  echo "Service did not become fully ready. Recent container logs:"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail 200 mt5proxy || true
  exit 1
fi

python tests/external_test_all_ops.py \
  --base-url "$BASE_URL" \
  --api-key "$API_KEY" \
  --symbol "$MT5_TEST_SYMBOL" \
  --volume "$MT5_TEST_VOLUME" \
  "${EXTRA_ARGS[@]}"

if [[ "$PLACE_TRADES" == "true" ]]; then
  echo "LOCAL_MUTATION_TESTS_PASSED"
else
  echo "LOCAL_READ_ONLY_TESTS_PASSED"
fi
