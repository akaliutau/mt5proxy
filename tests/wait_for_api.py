#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def request_json(url: str, api_key: str | None = None) -> tuple[int, object]:
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload: object = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--api-key", default="dev-api-key")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--ready", action="store_true", help="Also wait for /health/ready bridge socket readiness")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    deadline = time.monotonic() + args.timeout
    last_status: int | None = None
    last_payload: object | None = None

    while time.monotonic() < deadline:
        try:
            status, payload = request_json(f"{base}/health")
            last_status, last_payload = status, payload
            if status < 400:
                if not args.ready:
                    print("API_LIVE")
                    return 0
                ready_status, ready_payload = request_json(f"{base}/health/ready")
                last_status, last_payload = ready_status, ready_payload
                if ready_status < 400:
                    print("API_READY")
                    return 0
        except Exception as exc:  # noqa: BLE001 - diagnostic output for local smoke test
            last_status, last_payload = None, str(exc)
        time.sleep(5)

    print("Timed out waiting for service", file=sys.stderr)
    print("last_status=", last_status, file=sys.stderr)
    print("last_payload=", json.dumps(last_payload, indent=2, default=str), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
