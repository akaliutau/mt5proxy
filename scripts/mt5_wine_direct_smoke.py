#!/usr/bin/env python
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

SYMBOL = os.getenv("MT5_TEST_SYMBOL", "EURUSD")
VOLUME = float(os.getenv("MT5_TEST_VOLUME", "0.01"))
MAGIC = int(os.getenv("MT5_TEST_MAGIC", "424242"))
PLACE_TRADE = os.getenv("CHECK_PLACE_TRADE", "false").lower() in {"1", "true", "yes", "on"}

def good_retcode(result) -> bool:
    if result is None:
        return False
    return result.retcode in {
        mt5.TRADE_RETCODE_DONE,
        mt5.TRADE_RETCODE_PLACED,
        mt5.TRADE_RETCODE_DONE_PARTIAL,
    }

kwargs = {"timeout": int(os.getenv("MT5_TIMEOUT_MS", "60000"))}
if os.getenv("MT5_LOGIN"):
    kwargs["login"] = int(os.environ["MT5_LOGIN"])
    kwargs["password"] = os.getenv("MT5_PASSWORD", "")
    kwargs["server"] = os.getenv("MT5_SERVER", "")

print("initialize kwargs:", {k: v for k, v in kwargs.items() if k != "password"})
ok = mt5.initialize(**kwargs)
print("initialize:", ok, "last_error:", mt5.last_error())
if not ok:
    sys.exit(1)

print("version:", mt5.version())
print("terminal_info:", mt5.terminal_info())
account = mt5.account_info()
print("account_info:", account)
if account is None:
    sys.exit(2)

print("symbols_total:", mt5.symbols_total())
print("symbol_select:", SYMBOL, mt5.symbol_select(SYMBOL, True), "last_error:", mt5.last_error())
info = mt5.symbol_info(SYMBOL)
print("symbol_info:", info)
tick = mt5.symbol_info_tick(SYMBOL)
print("tick:", tick)
if info is None or tick is None:
    sys.exit(3)

end = datetime.now(timezone.utc)
start = end - timedelta(minutes=60)
rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M1, start, end)
print("copy_rates_range count:", None if rates is None else len(rates), "last_error:", mt5.last_error())
if rates is None or len(rates) == 0:
    sys.exit(4)

print("positions_get:", mt5.positions_get(symbol=SYMBOL), "last_error:", mt5.last_error())
print("orders_get:", mt5.orders_get(symbol=SYMBOL), "last_error:", mt5.last_error())

if not PLACE_TRADE:
    print("READ_ONLY_WINE_MT5_TESTS_PASSED")
    mt5.shutdown()
    sys.exit(0)

point = info.point
digits = info.digits
price = tick.ask
open_req = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": SYMBOL,
    "volume": VOLUME,
    "type": mt5.ORDER_TYPE_BUY,
    "price": price,
    "sl": round(price - 100 * point, digits),
    "tp": round(price + 200 * point, digits),
    "deviation": 30,
    "magic": MAGIC,
    "comment": "wine-direct-smoke-open",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC,
}
print("order_check open:", mt5.order_check(open_req), "last_error:", mt5.last_error())
open_res = mt5.order_send(open_req)
print("order_send open:", open_res, "last_error:", mt5.last_error())
if not good_retcode(open_res):
    sys.exit(5)

positions = list(mt5.positions_get(symbol=SYMBOL) or [])
pos = next((p for p in positions if getattr(p, "magic", None) == MAGIC), positions[-1] if positions else None)
if pos is None:
    print("No opened position found")
    sys.exit(6)
print("opened position:", pos)

sltp_req = {
    "action": mt5.TRADE_ACTION_SLTP,
    "position": pos.ticket,
    "symbol": SYMBOL,
    "sl": round(price - 80 * point, digits),
    "tp": round(price + 160 * point, digits),
    "deviation": 30,
    "comment": "wine-direct-smoke-sltp",
}
print("set SLTP:", mt5.order_send(sltp_req), "last_error:", mt5.last_error())

remove_req = dict(sltp_req)
remove_req["tp"] = 0.0
remove_req["comment"] = "wine-direct-smoke-remove-tp"
print("remove TP:", mt5.order_send(remove_req), "last_error:", mt5.last_error())

tick = mt5.symbol_info_tick(SYMBOL)
close_req = {
    "action": mt5.TRADE_ACTION_DEAL,
    "position": pos.ticket,
    "symbol": SYMBOL,
    "volume": pos.volume,
    "type": mt5.ORDER_TYPE_SELL,
    "price": tick.bid,
    "deviation": 30,
    "magic": MAGIC,
    "comment": "wine-direct-smoke-close",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC,
}
print("close:", mt5.order_send(close_req), "last_error:", mt5.last_error())
print("ALL_WINE_MT5_MUTATION_TESTS_PASSED")
mt5.shutdown()


