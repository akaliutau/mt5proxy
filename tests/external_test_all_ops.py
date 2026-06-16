#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone

import requests


def pretty(obj):
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def req(method, url, api_key=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if api_key:
        headers["X-API-Key"] = api_key
    r = requests.request(method, url, headers=headers, timeout=120, **kwargs)
    try:
        payload = r.json()
    except Exception:
        payload = r.text
    print(f"\n{method} {url} -> {r.status_code}")
    pretty(payload)
    if r.status_code >= 400:
        raise SystemExit(f"request failed: {r.status_code}")
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--api-key", default="dev-api-key")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--volume", type=float, default=0.01)
    ap.add_argument("--place-trades", action="store_true")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    req("GET", f"{base}/health")
    req("GET", f"{base}/v1/bridge", args.api_key)
    req("GET", f"{base}/v1/account", args.api_key)
    req("GET", f"{base}/v1/symbols/{args.symbol}/tick", args.api_key)

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=2)
    bars = req(
        "GET",
        f"{base}/v1/bars",
        args.api_key,
        params={"symbol": args.symbol, "timeframe": "M1", "start": start.isoformat(), "end": end.isoformat()},
    )
    if not bars.get("bars"):
        raise SystemExit("no bars returned")

    req("GET", f"{base}/v1/positions", args.api_key, params={"symbol": args.symbol})

    if not args.place_trades:
        print("\nREAD_ONLY_API_TESTS_PASSED. Add --place-trades only on a demo account with TRADING_ENABLED=true.")
        return

    tick_payload = req("GET", f"{base}/v1/symbols/{args.symbol}/tick", args.api_key)
    tick = tick_payload["tick"]
    info = tick_payload["symbol_info"]
    point = info.get("point") or 0.0001
    digits = info.get("digits") or 5
    ask = tick["ask"]
    sl = round(ask - 100 * point, digits)
    tp = round(ask + 200 * point, digits)

    opened = req(
        "POST",
        f"{base}/v1/deals/open",
        args.api_key,
        json={"symbol": args.symbol, "side": "buy", "volume": args.volume, "sl": sl, "tp": tp, "type_filling": "FOK"},
    )
    result = opened.get("result") or {}
    retcode = result.get("retcode")
    if retcode not in {10008, 10009, 10010}:
        raise SystemExit(f"open retcode not success: {retcode}")

    time.sleep(2)
    pos_payload = req("GET", f"{base}/v1/positions", args.api_key, params={"symbol": args.symbol})
    positions = pos_payload.get("positions") or []
    if not positions:
        raise SystemExit("no position found after open")
    ticket = positions[-1]["ticket"]

    req(
        "POST",
        f"{base}/v1/positions/{ticket}/sltp",
        args.api_key,
        json={"sl": round(ask - 80 * point, digits), "tp": round(ask + 160 * point, digits)},
    )
    req("DELETE", f"{base}/v1/positions/{ticket}/sltp", args.api_key)
    req("POST", f"{base}/v1/deals/close", args.api_key, json={"ticket": ticket, "type_filling": "AUTO"})
    print("\nALL_API_MUTATION_TESTS_PASSED")


if __name__ == "__main__":
    main()


