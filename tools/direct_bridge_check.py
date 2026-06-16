#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
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
    symbol = os.getenv("MT5_TEST_SYMBOL", "EURUSD")
    volume = float(os.getenv("MT5_TEST_VOLUME", "0.01"))
    magic = int(os.getenv("MT5_TEST_MAGIC", "424242"))
    place_trade = os.getenv("CHECK_PLACE_TRADE", "false").lower() in {"1", "true", "yes", "on"}

    print(f"Connecting to mt5linux bridge at {host}:{port} ...")
    mt5 = MetaTrader5(host=host, port=port, timeout=int(os.getenv("MT5LINUX_TIMEOUT", "300")))

    init_kwargs: dict[str, Any] = {"timeout": int(os.getenv("MT5_TIMEOUT_MS", "60000"))}
    if os.getenv("MT5_LOGIN"):
        init_kwargs["login"] = int(os.environ["MT5_LOGIN"])
        init_kwargs["password"] = os.getenv("MT5_PASSWORD", "")
        init_kwargs["server"] = os.getenv("MT5_SERVER", "")

    print("initialize kwargs:", {k: v for k, v in init_kwargs.items() if k != "password"})
    ok = mt5.initialize(**init_kwargs)
    print("initialize:", ok, "last_error:", asdict(mt5.last_error()))
    if not ok:
        return 2

    print("version:", asdict(mt5.version()))
    print("terminal_info:", asdict(mt5.terminal_info()))
    account = mt5.account_info()
    print("account_info:", asdict(account))
    if account is None:
        return 3

    print("symbols_total:", mt5.symbols_total())
    print("symbol_select:", symbol, mt5.symbol_select(symbol, True), "last_error:", asdict(mt5.last_error()))
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    print("symbol_info:", asdict(info))
    print("tick:", asdict(tick))
    if info is None or tick is None:
        return 4

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=2)
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start, end)
    print("copy_rates_range M1 count:", None if rates is None else len(rates), "last_error:", asdict(mt5.last_error()))
    if rates is None or len(rates) == 0:
        return 5

    print("positions_get:", asdict(mt5.positions_get(symbol=symbol)), "last_error:", asdict(mt5.last_error()))
    print("orders_get:", asdict(mt5.orders_get(symbol=symbol)), "last_error:", asdict(mt5.last_error()))

    if not place_trade:
        print("READ_ONLY_BRIDGE_TESTS_PASSED. Set CHECK_PLACE_TRADE=true only on a DEMO account to test open/SLTP/close.")
        mt5.shutdown()
        return 0

    digits = info.digits
    point = info.point
    price = tick.ask
    open_req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "sl": round(price - 100 * point, digits),
        "tp": round(price + 200 * point, digits),
        "deviation": 30,
        "magic": magic,
        "comment": "direct-bridge-check-open",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    print("order_check open:", asdict(mt5.order_check(open_req)), "last_error:", asdict(mt5.last_error()))
    open_result = mt5.order_send(open_req)
    print("order_send open:", asdict(open_result), "last_error:", asdict(mt5.last_error()))
    if open_result is None or open_result.retcode not in {10008, 10009, 10010}:
        return 6

    time.sleep(2)
    positions = mt5.positions_get(symbol=symbol) or []
    pos = None
    for item in positions:
        if getattr(item, "magic", None) == magic:
            pos = item
            break
    if pos is None and positions:
        pos = positions[-1]
    if pos is None:
        print("No position found after open")
        return 7

    sltp_req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": pos.ticket,
        "symbol": symbol,
        "sl": round(price - 80 * point, digits),
        "tp": round(price + 160 * point, digits),
        "deviation": 30,
        "comment": "direct-bridge-check-sltp",
    }
    print("order_send set SLTP:", asdict(mt5.order_send(sltp_req)), "last_error:", asdict(mt5.last_error()))

    remove_req = dict(sltp_req)
    remove_req["sl"] = 0.0
    remove_req["tp"] = 0.0
    remove_req["comment"] = "direct-bridge-check-remove-sltp"
    print("order_send remove SLTP:", asdict(mt5.order_send(remove_req)), "last_error:", asdict(mt5.last_error()))

    tick = mt5.symbol_info_tick(symbol)
    close_req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": pos.ticket,
        "symbol": symbol,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL,
        "price": tick.bid,
        "deviation": 30,
        "magic": magic,
        "comment": "direct-bridge-check-close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    print("order_send close:", asdict(mt5.order_send(close_req)), "last_error:", asdict(mt5.last_error()))
    mt5.shutdown()
    print("ALL_BRIDGE_MUTATION_TESTS_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


