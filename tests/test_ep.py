#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import requests

SUCCESS_RETCODES = {10008, 10009, 10010}


def pretty(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def req(method: str, url: str, api_key: str | None = None, **kwargs: Any) -> Any:
    headers = kwargs.pop("headers", {})
    if api_key:
        headers["X-API-Key"] = api_key
    resp = requests.request(method, url, headers=headers, timeout=120, **kwargs)
    try:
        payload = resp.json()
    except Exception:
        payload = resp.text
    print(f"\n{method} {url} -> {resp.status_code}")
    pretty(payload)
    if resp.status_code >= 400:
        raise SystemExit(f"request failed: {resp.status_code}")
    return payload


def assert_trade_ok(payload: dict[str, Any], label: str) -> None:
    retcode = payload.get("retcode") or (payload.get("result") or {}).get("retcode")
    assert retcode in SUCCESS_RETCODES, f"{label} retcode not success: {retcode}"


def result_ticket(payload: dict[str, Any]) -> int:
    ticket = (payload.get("result") or {}).get("order")
    assert ticket, f"order_send result does not include an order ticket: {payload}"
    return int(ticket)


def round_price(value: float, digits: int) -> float:
    return round(float(value), int(digits))


class Api:
    def __init__(self, args: argparse.Namespace):
        self.base = args.base_url.rstrip("/")
        self.api_key = args.api_key
        self.symbol = args.symbol
        self.volume = args.volume
        self.side = args.side
        self.order_kind = args.order_kind
        self.distance_points = args.distance_points
        self.sl_points = args.sl_points
        self.tp_points = args.tp_points
        self.trigger_price = args.trigger_price
        self.watch_seconds = args.watch_seconds
        self.magic = args.magic
        self.type_filling = args.type_filling

    def unique_comment(self, prefix: str) -> str:
        return f"{prefix}-{int(time.time())}"

    def health(self) -> None:
        payload = req("GET", f"{self.base}/health")
        assert payload.get("ok") is True

    def status(self) -> None:
        payload = req("GET", f"{self.base}/v1/status", self.api_key)
        assert payload.get("ok") is True
        assert isinstance(payload.get("terminal_info"), dict)
        assert isinstance(payload.get("account"), dict)
        print("MANUAL_CHECK: compare account, connected, and trade flags with MT5 terminal status.")

    def account(self) -> None:
        payload = req("GET", f"{self.base}/v1/account", self.api_key)
        assert isinstance(payload.get("account"), dict)
        print("MANUAL_CHECK: account.login/server/balance should match the MT5 account shown in the terminal.")

    def tick(self) -> dict[str, Any]:
        payload = req("GET", f"{self.base}/v1/symbols/{self.symbol}/tick", self.api_key)
        assert isinstance(payload.get("tick"), dict)
        assert payload["tick"].get("bid") is not None or payload["tick"].get("ask") is not None
        return payload

    def bars(self) -> None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=2)
        payload = req(
            "GET",
            f"{self.base}/v1/bars",
            self.api_key,
            params={"symbol": self.symbol, "timeframe": "M1", "start": start.isoformat(), "end": end.isoformat()},
        )
        assert payload.get("bars"), "no bars returned"

    def positions_payload(self) -> dict[str, Any]:
        payload = req("GET", f"{self.base}/v1/positions", self.api_key, params={"symbol": self.symbol})
        assert isinstance(payload.get("positions"), list)
        return payload

    def positions(self) -> None:
        self.positions_payload()
        print("MANUAL_CHECK: open positions list should match MT5 Trade tab for this symbol.")

    def orders_payload(self, ticket: int | None = None) -> dict[str, Any]:
        params = {"ticket": ticket} if ticket is not None else {"symbol": self.symbol}
        payload = req("GET", f"{self.base}/v1/orders", self.api_key, params=params)
        assert isinstance(payload.get("orders"), list)
        return payload

    def orders(self) -> None:
        self.orders_payload()
        print("MANUAL_CHECK: pending orders list should match MT5 Trade tab for this symbol.")

    def mt5_call(self) -> None:
        payload = req("POST", f"{self.base}/v1/mt5/call/terminal_info", self.api_key, json={})
        assert isinstance(payload.get("result"), dict)
        payload = req("POST", f"{self.base}/v1/mt5/call/positions_get", self.api_key, json={"kwargs": {"symbol": self.symbol}})
        assert isinstance(payload.get("result"), list) or payload.get("result") is None

    def price_context(self) -> tuple[dict[str, Any], dict[str, Any], float, int]:
        tick_payload = self.tick()
        tick = tick_payload["tick"]
        info = tick_payload["symbol_info"]
        point = float(info.get("point") or 0.0001)
        digits = int(info.get("digits") or 5)
        return tick, info, point, digits

    def sl_tp_for_side(self, side: str, entry_price: float, point: float, digits: int) -> tuple[float, float]:
        if side == "buy":
            return (
                round_price(entry_price - self.sl_points * point, digits),
                round_price(entry_price + self.tp_points * point, digits),
            )
        return (
            round_price(entry_price + self.sl_points * point, digits),
            round_price(entry_price - self.tp_points * point, digits),
        )

    def pending_price(self, side: str, order_kind: str) -> tuple[float, float | None, float, int]:
        tick, _info, point, digits = self.price_context()
        ask = float(tick["ask"])
        bid = float(tick["bid"])
        distance = self.distance_points * point

        if self.trigger_price is not None:
            price = float(self.trigger_price)
        elif side == "buy" and order_kind == "limit":
            price = ask - distance
        elif side == "sell" and order_kind == "limit":
            price = bid + distance
        elif side == "buy":  # buy stop or buy stop-limit
            price = ask + distance
        else:  # sell stop or sell stop-limit
            price = bid - distance

        price = round_price(price, digits)
        stoplimit = None
        if order_kind == "stop_limit":
            offset = max(1, self.distance_points // 4) * point
            stoplimit = round_price(price - offset if side == "buy" else price + offset, digits)
        assert price > 0, f"computed invalid pending price {price}; increase --distance-points or pass --trigger-price"
        return price, stoplimit, point, digits

    def nudge_pending_price(self, side: str, order_kind: str, old_price: float, point: float, digits: int) -> float:
        # Nudge farther away from the current market so the order normally remains pending during modify/cancel tests.
        delta = max(1, self.distance_points // 10) * point
        if side == "buy" and order_kind == "limit":
            return round_price(old_price - delta, digits)
        if side == "sell" and order_kind == "limit":
            return round_price(old_price + delta, digits)
        if side == "buy":
            return round_price(old_price + delta, digits)
        return round_price(old_price - delta, digits)

    def open_market(self) -> None:
        tick, _info, point, digits = self.price_context()
        entry = float(tick["ask"] if self.side == "buy" else tick["bid"])
        sl, tp = self.sl_tp_for_side(self.side, entry, point, digits)
        opened = req(
            "POST",
            f"{self.base}/v1/deals/open",
            self.api_key,
            json={
                "symbol": self.symbol,
                "side": self.side,
                "volume": self.volume,
                "sl": sl,
                "tp": tp,
                "magic": self.magic,
                "type_filling": self.type_filling,
                #"comment": self.unique_comment("mt5-proxy-open-market"),
            },
        )
        assert_trade_ok(opened, "open_market")
        print("MANUAL_CHECK_NOW: MT5 should show a new market position with attached SL/TP.")

    def find_opened_position(self, opened: dict[str, Any]) -> dict[str, Any]:
        ticket = (opened.get("result") or {}).get("order")
        if ticket:
            by_ticket = req("GET", f"{self.base}/v1/positions", self.api_key, params={"ticket": ticket})
            positions = by_ticket.get("positions") or []
            if positions:
                return positions[0]

        positions = self.positions_payload().get("positions") or []
        candidates = [p for p in positions if p.get("symbol") == self.symbol and p.get("magic") == self.magic]
        assert candidates, "could not find opened position by result.order or symbol/magic"
        return sorted(candidates, key=lambda p: (p.get("time_update") or p.get("time") or 0, p.get("ticket") or 0))[-1]

    def open_position_for_close_test(self) -> dict[str, Any]:
        tick, _info, point, digits = self.price_context()
        entry = float(tick["ask"] if self.side == "buy" else tick["bid"])
        sl, tp = self.sl_tp_for_side(self.side, entry, point, digits)
        opened = req(
            "POST",
            f"{self.base}/v1/deals/open",
            self.api_key,
            json={
                "symbol": self.symbol,
                "side": self.side,
                "volume": self.volume,
                "sl": sl,
                "tp": tp,
                "magic": self.magic,
                "type_filling": self.type_filling,
                #"comment": self.unique_comment("mt5-proxy-flow-open"),
            },
        )
        assert_trade_ok(opened, "open_for_close_test")
        time.sleep(2)
        pos = self.find_opened_position(opened)
        assert pos.get("sl") or pos.get("tp"), "opened position does not show SL/TP; broker may have rejected attached stops"
        return pos

    def close_position(self, pos: dict[str, Any], remove_sltp_before_close: bool) -> dict[str, Any]:
        closed = req(
            "POST",
            f"{self.base}/v1/deals/close",
            self.api_key,
            json={
                "ticket": pos["ticket"],
                "magic": self.magic,
                "type_filling": self.type_filling,
                "remove_sltp_before_close": remove_sltp_before_close,
                "verify": True,
                #"comment": self.unique_comment("mt5-proxy-flow-close"),
            },
        )
        assert_trade_ok(closed, "close_position")
        assert closed.get("position_after_close") == [], "position still exists after full close; inspect retcode/result for partial fill"
        return closed

    def flow_close_sltp(self) -> None:
        pos = self.open_position_for_close_test()
        #pos = {"ticket": 9126287001}
        closed = self.close_position(pos, remove_sltp_before_close=False)
        assert closed.get("sltp_cleanup") is None
        assert "full_close_removes" in closed.get("sltp_lifecycle", "")
        print("FLOW_CHECK: Full market close removed the position. No separate SL/TP cleanup was required.")

    def flow_remove_before_close(self) -> None:
        pos = self.open_position_for_close_test()
        closed = self.close_position(pos, remove_sltp_before_close=True)
        cleanup = closed.get("sltp_cleanup")
        assert isinstance(cleanup, dict) and cleanup.get("ok") is True, "pre-close SL/TP cleanup did not run successfully"
        print("FLOW_CHECK: Explicit pre-close SL/TP removal ran first, then the position was closed.")

    def pending(self) -> None:
        side = self.side
        order_kind = self.order_kind
        price, stoplimit, point, digits = self.pending_price(side, order_kind)
        sl, tp = self.sl_tp_for_side(side, price, point, digits)
        request_body: dict[str, Any] = {
            "symbol": self.symbol,
            "side": side,
            "order_kind": order_kind,
            "volume": self.volume,
            "price": 1.16016, #price,
            "sl": sl,
            "tp": tp,
            "magic": self.magic,
            "type_filling": self.type_filling,
            "comment": self.unique_comment("mt5-proxy-pending"),
        }
        if stoplimit is not None:
            request_body["stoplimit"] = stoplimit

        placed = req("POST", f"{self.base}/v1/orders/pending", self.api_key, json=request_body)
        assert_trade_ok(placed, "place_pending")
        ticket = result_ticket(placed)

        order_payload = self.orders_payload(ticket)
        assert order_payload.get("orders"), "pending order not found after placement"

        new_price = self.nudge_pending_price(side, order_kind, price, point, digits)
        new_sl, new_tp = self.sl_tp_for_side(side, new_price, point, digits)
        modify_body: dict[str, Any] = {"price": new_price, "sl": new_sl, "tp": new_tp}
        if stoplimit is not None:
            modify_body["stoplimit"] = self.nudge_pending_price(side, order_kind, stoplimit, point, digits)
        modified = req("POST", f"{self.base}/v1/orders/{ticket}/modify", self.api_key, json=modify_body)
        assert_trade_ok(modified, "modify_pending")
        assert modified.get("order_after_modify"), "pending order not found after modify"

        removed = req("DELETE", f"{self.base}/v1/orders/{ticket}", self.api_key)
        assert_trade_ok(removed, "remove_pending")
        assert removed.get("order_after_remove") == [], "pending order still exists after remove"
        print("FLOW_CHECK: Pending order with SL/TP was placed, modified, and removed.")

    def pending_trigger_watch(self) -> None:
        # A trigger cannot be forced by the proxy; this watches a normal pending order and cleans it up if not triggered.
        side = self.side
        order_kind = self.order_kind if self.order_kind in {"stop", "stop_limit"} else "stop"
        before_tickets = {p.get("ticket") for p in (self.positions_payload().get("positions") or [])}
        price, stoplimit, point, digits = self.pending_price(side, order_kind)
        sl, tp = self.sl_tp_for_side(side, price, point, digits)
        request_body: dict[str, Any] = {
            "symbol": self.symbol,
            "side": side,
            "order_kind": order_kind,
            "volume": self.volume,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": self.magic,
            "type_filling": self.type_filling,
            "comment": self.unique_comment("mt5-proxy-trigger-watch"),
        }
        if stoplimit is not None:
            request_body["stoplimit"] = stoplimit

        placed = req("POST", f"{self.base}/v1/orders/pending", self.api_key, json=request_body)
        assert_trade_ok(placed, "place_pending_trigger_watch")
        ticket = result_ticket(placed)

        deadline = time.time() + self.watch_seconds
        triggered_position: dict[str, Any] | None = None
        order_alive = True
        while time.time() < deadline:
            order_alive = bool(self.orders_payload(ticket).get("orders"))
            positions = self.positions_payload().get("positions") or []
            new_positions = [p for p in positions if p.get("ticket") not in before_tickets and p.get("magic") == self.magic]
            if new_positions and not order_alive:
                triggered_position = sorted(new_positions, key=lambda p: (p.get("time_update") or p.get("time") or 0, p.get("ticket") or 0))[-1]
                break
            time.sleep(2)

        if triggered_position:
            print("FLOW_CHECK: Pending order triggered. Resulting position should carry the pending order SL/TP.")
            pretty(triggered_position)
            closed = self.close_position(triggered_position, remove_sltp_before_close=False)
            assert closed.get("position_after_close") == []
        elif order_alive:
            removed = req("DELETE", f"{self.base}/v1/orders/{ticket}", self.api_key)
            assert_trade_ok(removed, "cleanup_untriggered_pending")
            print("FLOW_CHECK: Pending order did not trigger within watch window; it was removed for cleanup.")
        else:
            print("FLOW_CHECK: Pending order no longer exists, but no new matching position was found. Inspect MT5 history.")

    def open_close_demo_trade(self) -> None:
        self.flow_close_sltp()


def main() -> int:
    parser = argparse.ArgumentParser(description="External API checks for a running MT5 proxy.")
    parser.add_argument(
        "case",
        nargs="?",
        default="health",
        choices=[
            "health",
            "status",
            "account",
            "tick",
            "bars",
            "positions",
            "orders",
            "open_market",
            "mt5-call",
            "trade",
            "flow-close-sltp",
            "flow-remove-before-close",
            "pending",
            "pending-trigger-watch",
        ],
    )
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.getenv("API_KEY", "dev-api-key"))
    parser.add_argument("--symbol", default=os.getenv("MT5_TEST_SYMBOL", "EURUSD"))
    parser.add_argument("--volume", type=float, default=float(os.getenv("MT5_TEST_VOLUME", "0.01")))
    parser.add_argument("--side", choices=["buy", "sell"], default=os.getenv("MT5_TEST_SIDE", "buy"))
    parser.add_argument("--order-kind", choices=["limit", "stop", "stop_limit"], default=os.getenv("MT5_TEST_ORDER_KIND", "limit"))
    parser.add_argument("--distance-points", type=int, default=int(os.getenv("MT5_TEST_DISTANCE_POINTS", "200")))
    parser.add_argument("--sl-points", type=int, default=int(os.getenv("MT5_TEST_SL_POINTS", "100")))
    parser.add_argument("--tp-points", type=int, default=int(os.getenv("MT5_TEST_TP_POINTS", "200")))
    parser.add_argument("--trigger-price", type=float, default=None)
    parser.add_argument("--watch-seconds", type=int, default=int(os.getenv("MT5_TEST_WATCH_SECONDS", "60")))
    parser.add_argument("--magic", type=int, default=int(os.getenv("MT5_TEST_MAGIC", "19")))
    parser.add_argument("--type-filling", default=os.getenv("MT5_TEST_TYPE_FILLING", "AUTO"), choices=["AUTO", "FOK", "IOC", "RETURN"])
    args = parser.parse_args()

    api = Api(args)
    cases: dict[str, Callable[[], None]] = {
        "health": api.health,
        "status": api.status,
        "account": api.account,
        "tick": api.tick,
        "bars": api.bars,
        "positions": api.positions,
        "orders": api.orders,
        "open_market": api.open_market,
        "mt5-call": api.mt5_call,
        "trade": api.open_close_demo_trade,
        "flow-close-sltp": api.flow_close_sltp,
        "flow-remove-before-close": api.flow_remove_before_close,
        "pending": api.pending,
        "pending-trigger-watch": api.pending_trigger_watch,
    }

    name = str(args.case)
    cases[name]()
    print(f"\n{name.upper().replace('-', '_')}_TEST_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
