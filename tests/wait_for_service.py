#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys, time
import requests

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base-url', default='http://127.0.0.1:8000')
    ap.add_argument('--api-key', default='dev-api-key')
    ap.add_argument('--timeout', type=int, default=300)
    args = ap.parse_args()
    deadline = time.time() + args.timeout
    last = None
    while time.time() < deadline:
        try:
            r = requests.get(args.base_url.rstrip() + '/ready?deep=true', headers={'X-API-Key': args.api_key}, timeout=10)
            if r.ok:
                print(r.text)
                return 0
            last = f'{r.status_code} {r.text[:500]}'
        except Exception as exc:
            last = repr(exc)
        print(f'waiting for ready: {last}', flush=True)
        time.sleep(5)
    print(f'timeout waiting for service readiness: {last}', file=sys.stderr)
    return 1
if __name__ == '__main__':
    raise SystemExit(main())
