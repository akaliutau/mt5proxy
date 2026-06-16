#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from typing import Any

from mt5linux import MetaTrader5


def asdict(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: asdict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        if hasattr(obj, "_asdict"):
            return {k: asdict(v) for k, v in obj._asdict().items()}
        return [asdict(v) for v in obj]
    if hasattr(obj, "tolist"):
        return asdict(obj.tolist())
    if hasattr(obj, "_asdict"):
        return {k: asdict(v) for k, v in obj._asdict().items()}
    return str(obj)


def main() -> int:
    host = os.getenv("MT5LINUX_HOST", "127.0.0.1")
    port = int(os.getenv("MT5LINUX_PORT", "8001"))
    timeout = int(os.getenv("MT5LINUX_TIMEOUT", "300"))
    init_timeout = int(os.getenv("MT5_TIMEOUT_MS", "60000"))
    require_account = os.getenv("BRIDGE_INIT_REQUIRE_ACCOUNT", "false").lower() in {"1", "true", "yes", "on"}

    payload: dict[str, Any] = {"host": host, "port": port, "initialize": False}
    try:
        mt5 = MetaTrader5(host=host, port=port, timeout=timeout)
        init_kwargs: dict[str, Any] = {"timeout": init_timeout}
        if os.getenv("MT5_LOGIN"):
            init_kwargs["login"] = int(os.environ["MT5_LOGIN"])
            init_kwargs["password"] = os.getenv("MT5_PASSWORD", "")
            init_kwargs["server"] = os.getenv("MT5_SERVER", "")
        payload["init_kwargs"] = {k: v for k, v in init_kwargs.items() if k != "password"}
        ok = mt5.initialize(**init_kwargs)
        payload["initialize"] = bool(ok)
        payload["last_error"] = asdict(mt5.last_error())
        if not ok:
            print(json.dumps(payload, indent=2, sort_keys=True, default=str))
            return 2
        payload["version"] = asdict(mt5.version())
        payload["terminal_info"] = asdict(mt5.terminal_info())
        if require_account:
            account = mt5.account_info()
            payload["account_present"] = account is not None
            payload["account"] = asdict(account)
            if account is None:
                print(json.dumps(payload, indent=2, sort_keys=True, default=str))
                return 3
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        mt5.shutdown()
        return 0
    except Exception as exc:  # diagnostic CLI used by supervisor/test harness
        payload["error"] = repr(exc)
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
