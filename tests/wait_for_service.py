#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import requests


def get_json(url: str, api_key: str | None = None) -> tuple[int | None, Any]:
    headers = {"X-API-Key": api_key} if api_key else {}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        try:
            payload: Any = r.json()
        except Exception:
            payload = r.text
        return r.status_code, payload
    except Exception as exc:
        return None, str(exc)


def main() -> int:
    ap = argparse.ArgumentParser(description="Wait for the MT5 proxy HTTP service from the host.")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--api-key", default="dev-api-key")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--deep-ready", action="store_true", help="Require /ready?deep=true, which verifies bridge + MT5 account.")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    deadline = time.time() + args.timeout
    last: tuple[str, int | None, Any] | None = None

    while time.time() < deadline:
        status, payload = get_json(f"{base}/health")
        last = ("/health", status, payload)
        if status == 200:
            ready_url = f"{base}/ready?deep={'true' if args.deep_ready else 'false'}"
            status, payload = get_json(ready_url, args.api_key)
            last = ("/ready", status, payload)
            if status == 200:
                print("SERVICE_READY")
                print(json.dumps(payload, indent=2, sort_keys=True, default=str))
                return 0
        time.sleep(args.interval)

    print("Timed out waiting for service readiness.", file=sys.stderr)
    if last:
        endpoint, status, payload = last
        print(f"Last response from {endpoint}: {status}", file=sys.stderr)
        print(json.dumps(payload, indent=2, sort_keys=True, default=str), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
