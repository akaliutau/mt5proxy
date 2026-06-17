from __future__ import annotations

import os
import socket
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

SERVICE_NAME = "mt5-wine-proxy"
SUCCESS_RETCODES = {10008, 10009, 10010}  # placed, done, done partial
UNSUPPORTED_FILLING_RETCODE = 10030

# Keep this table small and explicit. It is the stability layer that replaces
# strict dataclasses: every exposed MT5 call has one central null/empty policy,
# and handlers only decide endpoint-specific names such as "account" or "bars".
MT5_RESULT_POLICY: dict[str, dict[str, Any]] = {
    "account_info": {"kind": "one", "none_error": True},
    "terminal_info": {"kind": "one", "none_error": True},
    "version": {"kind": "one", "none_error": True},
    "symbol_info": {"kind": "one", "none_error": True, "error_status": 404},
    "symbol_info_tick": {"kind": "one", "none_error": True, "error_status": 404},
    "symbol_select": {"kind": "bool", "none_error": True, "false_error": True, "error_status": 400},
    "copy_rates_from": {"kind": "list", "none_error": True, "transform": "rows"},
    "copy_rates_from_pos": {"kind": "list", "none_error": True, "transform": "rows"},
    "copy_rates_range": {"kind": "list", "none_error": True, "transform": "rows"},
    "copy_ticks_from": {"kind": "list", "none_error": True, "transform": "rows"},
    "copy_ticks_range": {"kind": "list", "none_error": True, "transform": "rows"},
    "positions_get": {"kind": "list", "none_error": True},
    "orders_get": {"kind": "list", "none_error": True},
    "history_deals_get": {"kind": "list", "none_error": True},
    "history_orders_get": {"kind": "list", "none_error": True},
    "symbols_get": {"kind": "list", "none_error": True},
    "market_book_get": {"kind": "list", "none_error": True},
    "positions_total": {"kind": "one", "none_error": True},
    "orders_total": {"kind": "one", "none_error": True},
    "history_deals_total": {"kind": "one", "none_error": True},
    "history_orders_total": {"kind": "one", "none_error": True},
    "symbols_total": {"kind": "one", "none_error": True},
    "order_calc_margin": {"kind": "one", "none_error": True},
    "order_calc_profit": {"kind": "one", "none_error": True},
    "order_check": {"kind": "one", "none_error": True},
    "last_error": {"kind": "one", "none_error": False},
}

# Keep the proxy lifecycle-owned. These calls are safe to expose through the
# flexible endpoint because they do not execute a real trade. `order_send` stays
# behind the dedicated trading endpoints and TRADING_ENABLED guard.
READ_ONLY_MT5_METHODS = set(MT5_RESULT_POLICY)


def _env_true(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def _api_key_guard(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("API_KEY", "dev-api-key")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid API key")


def _asdict(obj: Any) -> Any:
    """Serialize MT5 namedtuples, numpy arrays/scalars, and plain objects."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _asdict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        if hasattr(obj, "_asdict"):
            return {k: _asdict(v) for k, v in obj._asdict().items()}
        return [_asdict(v) for v in obj]
    if hasattr(obj, "tolist"):
        return _asdict(obj.tolist())
    if hasattr(obj, "_asdict"):
        return {k: _asdict(v) for k, v in obj._asdict().items()}
    return str(obj)


def _array_to_rows(data: Any) -> list[Any]:
    if data is None:
        return []

    names = getattr(getattr(data, "dtype", None), "names", None)
    if not names:
        return _asdict(data) or []

    rows: list[dict[str, Any]] = []
    for row in data:
        item = {name: _asdict(row[name]) for name in names}
        if "time" in item:
            item["time_iso"] = datetime.fromtimestamp(int(item["time"]), tz=timezone.utc).isoformat()
        rows.append(item)
    return rows


def _parse_dt(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _maybe_parse_dt(value: str) -> Any:
    if "T" not in value and " " not in value:
        return value
    try:
        return _parse_dt(value)
    except ValueError:
        return value


def _decode_mt5_value(mt5: Any, value: Any) -> Any:
    """
    Decode small conveniences for the generic endpoint:
    - "MT5:TIMEFRAME_M1" -> mt5.TIMEFRAME_M1
    - ISO datetimes -> timezone-aware UTC datetimes
    """
    if isinstance(value, str):
        if value.startswith("MT5:"):
            name = value[4:]
            if not hasattr(mt5, name):
                raise HTTPException(status_code=400, detail=f"unknown MT5 constant {name}")
            return getattr(mt5, name)
        return _maybe_parse_dt(value)
    if isinstance(value, list):
        return [_decode_mt5_value(mt5, item) for item in value]
    if isinstance(value, dict):
        return {key: _decode_mt5_value(mt5, item) for key, item in value.items()}
    return value


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, bytes, bytearray)):
        return False
    try:
        return len(value) == 0  # type: ignore[arg-type]
    except TypeError:
        return False


def _last_error(mt5: Any) -> Any:
    try:
        return _asdict(mt5.last_error())
    except Exception as exc:  # noqa: BLE001 - keep diagnostics stable even when bridge is unhealthy
        return {"error": repr(exc)}


def _failure(method: str, message: str, *, last_error: Any = None, error: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "method": method, "message": message, "last_error": last_error}
    if error is not None:
        payload["error"] = error
    if extra:
        payload.update(extra)
    return payload


def _check_mt5_result(method: str, raw: Any, last_error: Any) -> None:
    policy = MT5_RESULT_POLICY.get(method, {"kind": "one", "none_error": False})
    status_code = int(policy.get("error_status", 502))

    if raw is None and policy.get("none_error", False):
        raise HTTPException(status_code=status_code, detail=_failure(method, f"{method} returned None", last_error=last_error))

    if raw is False and policy.get("false_error", False):
        raise HTTPException(status_code=status_code, detail=_failure(method, f"{method} returned False", last_error=last_error))


def _normalize_mt5_value(method: str, raw: Any) -> Any:
    policy = MT5_RESULT_POLICY.get(method, {"kind": "one"})
    if policy.get("transform") == "rows":
        return _array_to_rows(raw)

    value = _asdict(raw)
    if policy.get("kind") == "list":
        return value or []
    return value


def _invoke_mt5(mt5: Any, method: str, *args: Any, **kwargs: Any) -> tuple[Any, Any]:
    fn = getattr(mt5, method, None)
    if fn is None or not callable(fn):
        raise HTTPException(status_code=404, detail=f"unknown MT5 method: {method}")

    try:
        raw = fn(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - bridge/RPyC failures should become stable JSON
        raise HTTPException(status_code=502, detail=_failure(method, f"{method} raised an exception", last_error=_last_error(mt5), error=repr(exc))) from exc

    last_error = _last_error(mt5)
    _check_mt5_result(method, raw, last_error)
    return _normalize_mt5_value(method, raw), last_error


def _mt5_payload(mt5: Any, method: str, key: str = "result", *args: Any, include_method: bool = False, extra: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    value, last_error = _invoke_mt5(mt5, method, *args, **kwargs)
    payload: dict[str, Any] = {"ok": True, key: value, "empty": _empty(value), "last_error": last_error}
    if include_method:
        payload["method"] = method
    if extra:
        payload.update(extra)
    return payload


def _mt5_value(mt5: Any, method: str, *args: Any, **kwargs: Any) -> Any:
    value, _last_error_value = _invoke_mt5(mt5, method, *args, **kwargs)
    return value


def _connect_mt5(timeout_ms: int | None = None):
    try:
        from mt5linux import MetaTrader5
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"mt5linux import failed: {exc}") from exc

    init_kwargs: dict[str, Any] = {"timeout": timeout_ms if timeout_ms is not None else int(os.getenv("MT5_TIMEOUT_MS", "60000"))}
    if os.getenv("MT5_LOGIN"):
        init_kwargs["login"] = int(os.environ["MT5_LOGIN"])
        init_kwargs["password"] = os.getenv("MT5_PASSWORD", "")
        init_kwargs["server"] = os.getenv("MT5_SERVER", "")

    attempts = max(1, int(os.getenv("MT5_INIT_RETRIES", "2")))
    delay = float(os.getenv("MT5_INIT_RETRY_DELAY_SECONDS", "0.5"))
    last_error: Any = None
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        mt5 = None
        try:
            mt5 = MetaTrader5(
                host=os.getenv("MT5LINUX_HOST", "127.0.0.1"),
                port=int(os.getenv("MT5LINUX_PORT", "8001")),
                timeout=int(os.getenv("MT5LINUX_TIMEOUT", "300")),
            )
            ok = mt5.initialize(**init_kwargs)
            last_error = _last_error(mt5)
            if ok:
                return mt5
            mt5.shutdown()
        except Exception as exc:  # noqa: BLE001 - connection/initialize diagnostic
            last_exc = exc
            if mt5 is not None:
                try:
                    mt5.shutdown()
                except Exception:
                    pass
        if attempt < attempts:
            time.sleep(delay)

    detail = _failure(
        "initialize",
        "mt5.initialize failed",
        last_error=last_error,
        error=repr(last_exc) if last_exc else None,
        extra={"attempts": attempts, "init_kwargs": {k: v for k, v in init_kwargs.items() if k != "password"}},
    )
    raise HTTPException(status_code=503, detail=detail)


@contextmanager
def _mt5_session(timeout_ms: int | None = None) -> Iterator[Any]:
    mt5 = _connect_mt5(timeout_ms=timeout_ms)
    try:
        yield mt5
    finally:
        mt5.shutdown()


def _mt5_read(fn: Any, *, timeout_ms: int | None = None) -> Any:
    """Retry only read/status calls. Trade sends are intentionally not retried."""
    attempts = max(1, int(os.getenv("MT5_READ_RETRIES", "2")))
    delay = float(os.getenv("MT5_READ_RETRY_DELAY_SECONDS", "0.5"))
    last_exc: HTTPException | Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            with _mt5_session(timeout_ms=timeout_ms) as mt5:
                return fn(mt5)
        except HTTPException as exc:
            last_exc = exc
            if exc.status_code < 500 or attempt >= attempts:
                raise
        except Exception as exc:  # noqa: BLE001 - stabilize unexpected bridge/client failures
            last_exc = exc
            if attempt >= attempts:
                raise HTTPException(
                    status_code=502,
                    detail=_failure("read", "MT5 read operation failed", last_error=None, error=repr(exc), extra={"attempts": attempts}),
                ) from exc
        time.sleep(delay)

    if isinstance(last_exc, HTTPException):
        raise last_exc
    raise HTTPException(status_code=502, detail=_failure("read", "MT5 read operation failed", last_error=None, error=repr(last_exc)))


def _require_trading_enabled() -> None:
    if not _env_true("TRADING_ENABLED"):
        raise HTTPException(status_code=403, detail="TRADING_ENABLED=false")


def _filling_map(mt5: Any) -> dict[str, int]:
    return {
        "FOK": mt5.ORDER_FILLING_FOK,
        "IOC": mt5.ORDER_FILLING_IOC,
        "RETURN": mt5.ORDER_FILLING_RETURN,
    }


def _filling_candidates(mt5: Any, requested: str) -> list[tuple[str, int]]:
    requested = requested.upper()
    values = _filling_map(mt5)
    if requested == "AUTO":
        return [(name, values[name]) for name in ("FOK", "IOC", "RETURN")]
    if requested not in values:
        raise HTTPException(status_code=400, detail=f"unknown type_filling {requested}; use AUTO, FOK, IOC, or RETURN")
    return [(requested, values[requested])]


def _trade_payload(mt5: Any, method: str, request: dict[str, Any], result: Any, *, attempts: list[dict[str, Any]] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    serialized_result = _asdict(result)
    retcode = getattr(result, "retcode", None)
    payload: dict[str, Any] = {
        "ok": retcode in SUCCESS_RETCODES,
        "method": method,
        "request": request,
        "result": serialized_result,
        "retcode": retcode,
        "empty": result is None,
        "last_error": _last_error(mt5),
    }
    if attempts is not None:
        payload["filling_attempts"] = attempts
    if extra:
        payload.update(extra)
    return payload


def _send_order_with_filling_fallback(mt5: Any, base_request: dict[str, Any], type_filling: str) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    final_request: dict[str, Any] | None = None
    result = None

    for name, value in _filling_candidates(mt5, type_filling):
        request = dict(base_request)
        request["type_filling"] = value
        final_request = request
        try:
            result = mt5.order_send(request)
        except Exception as exc:  # noqa: BLE001 - do not retry mutations; return a stable failure
            return {
                "ok": False,
                "method": "order_send",
                "request": request,
                "result": None,
                "retcode": None,
                "empty": True,
                "filling_attempts": attempts,
                "last_error": _last_error(mt5),
                "error": repr(exc),
            }

        retcode = getattr(result, "retcode", None)
        attempts.append(
            {
                "type_filling_name": name,
                "type_filling": value,
                "retcode": retcode,
                "comment": getattr(result, "comment", None),
                "last_error": _last_error(mt5),
            }
        )

        if retcode in SUCCESS_RETCODES:
            break
        if retcode != UNSUPPORTED_FILLING_RETCODE:
            break

    return _trade_payload(mt5, "order_send", final_request or base_request, result, attempts=attempts)


def _send_order_direct(mt5: Any, request: dict[str, Any]) -> dict[str, Any]:
    try:
        result = mt5.order_send(request)
    except Exception as exc:  # noqa: BLE001 - do not retry mutations
        raise HTTPException(status_code=502, detail=_failure("order_send", "order_send raised an exception", last_error=_last_error(mt5), error=repr(exc))) from exc
    return _trade_payload(mt5, "order_send", request, result)


def _order_time_map(mt5: Any) -> dict[str, int]:
    return {
        "GTC": mt5.ORDER_TIME_GTC,
        "DAY": mt5.ORDER_TIME_DAY,
        "SPECIFIED": mt5.ORDER_TIME_SPECIFIED,
        "SPECIFIED_DAY": mt5.ORDER_TIME_SPECIFIED_DAY,
    }


def _order_time_value(mt5: Any, requested: str | int) -> int:
    if isinstance(requested, int):
        return requested
    requested = requested.upper()
    values = _order_time_map(mt5)
    if requested not in values:
        raise HTTPException(status_code=400, detail=f"unknown type_time {requested}; use GTC, DAY, SPECIFIED, or SPECIFIED_DAY")
    return values[requested]


def _apply_expiration(request: dict[str, Any], expiration: str | None) -> None:
    if expiration:
        request["expiration"] = _parse_dt(expiration)


def _pending_order_type(mt5: Any, side: str, order_kind: str) -> int:
    key = (side.lower(), order_kind.lower())
    values = {
        ("buy", "limit"): mt5.ORDER_TYPE_BUY_LIMIT,
        ("sell", "limit"): mt5.ORDER_TYPE_SELL_LIMIT,
        ("buy", "stop"): mt5.ORDER_TYPE_BUY_STOP,
        ("sell", "stop"): mt5.ORDER_TYPE_SELL_STOP,
        ("buy", "stop_limit"): mt5.ORDER_TYPE_BUY_STOP_LIMIT,
        ("sell", "stop_limit"): mt5.ORDER_TYPE_SELL_STOP_LIMIT,
    }
    if key not in values:
        raise HTTPException(status_code=400, detail="invalid pending order side/order_kind combination")
    return values[key]


def _build_sltp_request(mt5: Any, position: dict[str, Any], *, sl: float, tp: float, deviation: int, comment: str) -> dict[str, Any]:
    return {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position["ticket"],
        "symbol": position["symbol"],
        "sl": sl,
        "tp": tp,
        "deviation": deviation,
        "comment": comment,
    }


def _select_symbol(mt5: Any, symbol: str) -> None:
    _invoke_mt5(mt5, "symbol_select", symbol, True)


class Mt5CallRequest(BaseModel):
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class OpenDealRequest(BaseModel):
    symbol: str = "EURUSD"
    side: str = Field(pattern="^(buy|sell)$")
    volume: float = Field(default=0.01, gt=0)
    sl: Optional[float] = None
    tp: Optional[float] = None
    deviation: int = 30
    magic: int = 424242
    comment: str = "mt5-proxy-open"
    type_filling: str = "AUTO"  # AUTO, FOK, IOC, RETURN


class CloseDealRequest(BaseModel):
    ticket: int
    volume: Optional[float] = Field(default=None, gt=0)
    deviation: int = 30
    magic: int = 424242
    type_filling: str = "AUTO"  # AUTO, FOK, IOC, RETURN
    comment: str = "mt5-proxy-close"
    # Normally false: on a full close MT5 removes position-attached SL/TP by removing the position.
    # True is useful for deterministic testing or for brokers/accounts where you want a two-step flow.
    remove_sltp_before_close: bool = False
    verify: bool = True


class SetSltpRequest(BaseModel):
    sl: Optional[float] = None
    tp: Optional[float] = None
    deviation: int = 30
    comment: str = "mt5-proxy-sltp"


class PendingOrderRequest(BaseModel):
    """Place a pending order that can later trigger a deal/position carrying its SL/TP."""

    symbol: str = "EURUSD"
    side: str = Field(pattern="^(buy|sell)$")
    order_kind: str = Field(default="limit", pattern="^(limit|stop|stop_limit)$")
    volume: float = Field(default=0.01, gt=0)
    price: float = Field(gt=0)
    stoplimit: Optional[float] = Field(default=None, gt=0)
    sl: Optional[float] = None
    tp: Optional[float] = None
    deviation: int = 30
    magic: int = 424242
    comment: str = "mt5-proxy-pending"
    type_time: str = "GTC"  # GTC, DAY, SPECIFIED, SPECIFIED_DAY
    expiration: Optional[str] = None  # UTC ISO time; required for SPECIFIED/SPECIFIED_DAY on many brokers
    type_filling: str = "AUTO"  # AUTO, FOK, IOC, RETURN


class ModifyPendingOrderRequest(BaseModel):
    price: Optional[float] = Field(default=None, gt=0)
    stoplimit: Optional[float] = Field(default=None, gt=0)
    sl: Optional[float] = None
    tp: Optional[float] = None
    remove_sl: bool = False
    remove_tp: bool = False
    deviation: int = 30
    comment: str = "mt5-proxy-modify-pending"
    type_time: Optional[str] = None  # omitted means preserve current MT5 order value
    expiration: Optional[str] = None


app = FastAPI(title="MT5 Wine Proxy", version="0.5.0")


@app.get("/health")
def health():
    return {"ok": True, "service": SERVICE_NAME}


@app.get("/health/live")
def health_live():
    return {"ok": True, "service": SERVICE_NAME}


@app.get("/health/ready")
def health_ready():
    host = os.getenv("MT5LINUX_HOST", "127.0.0.1")
    port = int(os.getenv("MT5LINUX_PORT", "8001"))
    try:
        with socket.create_connection((host, port), timeout=3):
            pass
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail={"ok": False, "service": SERVICE_NAME, "bridge": {"host": host, "port": port, "listening": False}, "error": str(exc)},
        ) from exc

    def check(mt5: Any) -> dict[str, Any]:
        terminal = _mt5_value(mt5, "terminal_info")
        return {
            "ok": True,
            "service": SERVICE_NAME,
            "bridge": {"host": host, "port": port, "listening": True, "initialize": True},
            "version": _mt5_value(mt5, "version"),
            "terminal_info": terminal,
            "empty": False,
            "last_error": _last_error(mt5),
        }

    return _mt5_read(check, timeout_ms=int(os.getenv("READY_MT5_TIMEOUT_MS", "15000")))


@app.get("/v1/bridge", dependencies=[Depends(_api_key_guard)])
def bridge_status():
    def read(mt5: Any) -> dict[str, Any]:
        terminal = _mt5_value(mt5, "terminal_info")
        return {
            "ok": True,
            "version": _mt5_value(mt5, "version"),
            "terminal_info": terminal,
            "empty": False,
            "last_error": _last_error(mt5),
        }

    return _mt5_read(read)


@app.get("/v1/status", dependencies=[Depends(_api_key_guard)])
def status():
    """Compact MT5 status for dashboards and manual checks."""

    def read(mt5: Any) -> dict[str, Any]:
        terminal = _mt5_value(mt5, "terminal_info")
        account = _mt5_value(mt5, "account_info")
        return {
            "ok": True,
            "empty": False,
            "version": _mt5_value(mt5, "version"),
            "terminal_info": terminal,
            "account": account,
            "trading": {
                "proxy_enabled": _env_true("TRADING_ENABLED"),
                "terminal_trade_allowed": terminal.get("trade_allowed"),
                "terminal_tradeapi_disabled": terminal.get("tradeapi_disabled"),
                "account_trade_allowed": account.get("trade_allowed"),
                "account_trade_expert": account.get("trade_expert"),
            },
            "counts": {
                "symbols": _mt5_value(mt5, "symbols_total"),
                "orders": _mt5_value(mt5, "orders_total"),
                "positions": _mt5_value(mt5, "positions_total"),
            },
            "last_error": _last_error(mt5),
        }

    return _mt5_read(read)


@app.get("/v1/account", dependencies=[Depends(_api_key_guard)])
def account_info():
    return _mt5_read(lambda mt5: _mt5_payload(mt5, "account_info", "account"))


@app.post("/v1/mt5/call/{method}", dependencies=[Depends(_api_key_guard)])
def mt5_call(method: str, req: Mt5CallRequest):
    """
    Flexible read-only escape hatch for official MetaTrader5 Python API calls.

    Examples:
      {"kwargs": {"symbol": "EURUSD"}} for positions_get
      {"args": ["EURUSD", "MT5:TIMEFRAME_M1", "2026-06-17T08:00:00Z", "2026-06-17T09:00:00Z"]} for copy_rates_range
    """
    if method not in READ_ONLY_MT5_METHODS or method.startswith("_"):
        raise HTTPException(status_code=404, detail=f"MT5 method is not exposed: {method}")

    def read(mt5: Any) -> dict[str, Any]:
        args = [_decode_mt5_value(mt5, item) for item in req.args]
        kwargs = {key: _decode_mt5_value(mt5, item) for key, item in req.kwargs.items()}
        return _mt5_payload(mt5, method, "result", *args, include_method=True, **kwargs)

    return _mt5_read(read)


@app.get("/v1/symbols/{symbol}/tick", dependencies=[Depends(_api_key_guard)])
def tick(symbol: str):
    def read(mt5: Any) -> dict[str, Any]:
        _select_symbol(mt5, symbol)
        info = _mt5_value(mt5, "symbol_info", symbol)
        tick_data = _mt5_value(mt5, "symbol_info_tick", symbol)
        return {
            "ok": True,
            "symbol": symbol,
            "symbol_info": info,
            "tick": tick_data,
            "empty": False,
            "last_error": _last_error(mt5),
        }

    return _mt5_read(read)


@app.get("/v1/bars", dependencies=[Depends(_api_key_guard)])
def bars(
    symbol: str = Query(...),
    timeframe: str = Query("M1"),
    start: str = Query(..., description="UTC ISO time, e.g. 2026-06-16T08:00:00Z"),
    end: str = Query(..., description="UTC ISO time"),
):
    def read(mt5: Any) -> dict[str, Any]:
        tf_name = f"TIMEFRAME_{timeframe.upper()}"
        if not hasattr(mt5, tf_name):
            raise HTTPException(status_code=400, detail=f"unknown timeframe {timeframe}")
        _select_symbol(mt5, symbol)
        return _mt5_payload(
            mt5,
            "copy_rates_range",
            "bars",
            symbol,
            getattr(mt5, tf_name),
            _parse_dt(start),
            _parse_dt(end),
            extra={"symbol": symbol, "timeframe": timeframe},
        )

    return _mt5_read(read)


@app.get("/v1/orders", dependencies=[Depends(_api_key_guard)])
def orders(symbol: str | None = None, ticket: int | None = None):
    def read(mt5: Any) -> dict[str, Any]:
        if ticket is not None:
            return _mt5_payload(mt5, "orders_get", "orders", ticket=ticket)
        if symbol:
            return _mt5_payload(mt5, "orders_get", "orders", symbol=symbol)
        return _mt5_payload(mt5, "orders_get", "orders")

    return _mt5_read(read)


@app.get("/v1/positions", dependencies=[Depends(_api_key_guard)])
def positions(symbol: str | None = None, ticket: int | None = None):
    def read(mt5: Any) -> dict[str, Any]:
        if ticket is not None:
            return _mt5_payload(mt5, "positions_get", "positions", ticket=ticket)
        if symbol:
            return _mt5_payload(mt5, "positions_get", "positions", symbol=symbol)
        return _mt5_payload(mt5, "positions_get", "positions")

    return _mt5_read(read)


@app.post("/v1/deals/open", dependencies=[Depends(_api_key_guard)])
def open_deal(req: OpenDealRequest):
    _require_trading_enabled()
    with _mt5_session() as mt5:
        _select_symbol(mt5, req.symbol)
        info = _mt5_value(mt5, "symbol_info", req.symbol)
        tick_data = _mt5_value(mt5, "symbol_info_tick", req.symbol)

        side_buy = req.side.lower() == "buy"
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": req.symbol,
            "volume": req.volume,
            "type": mt5.ORDER_TYPE_BUY if side_buy else mt5.ORDER_TYPE_SELL,
            "price": tick_data["ask"] if side_buy else tick_data["bid"],
            "deviation": req.deviation,
            "magic": req.magic,
            "comment": req.comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }
        if req.sl is not None:
            request["sl"] = req.sl
        if req.tp is not None:
            request["tp"] = req.tp

        payload = _send_order_with_filling_fallback(mt5, request, req.type_filling)
        payload["symbol_filling_mode"] = info.get("filling_mode")
        payload["symbol_trade_exemode"] = info.get("trade_exemode")
        return payload


@app.post("/v1/deals/close", dependencies=[Depends(_api_key_guard)])
def close_deal(req: CloseDealRequest):
    _require_trading_enabled()
    with _mt5_session() as mt5:
        pos_list = _mt5_value(mt5, "positions_get", ticket=req.ticket)
        if not pos_list:
            raise HTTPException(status_code=404, detail="position not found")

        pos = pos_list[0]
        _select_symbol(mt5, pos["symbol"])
        info = _mt5_value(mt5, "symbol_info", pos["symbol"])
        tick_data = _mt5_value(mt5, "symbol_info_tick", pos["symbol"])

        position_volume = float(pos["volume"])
        close_volume = position_volume if req.volume is None else float(req.volume)
        if close_volume <= 0:
            raise HTTPException(status_code=400, detail="close volume must be positive")
        if close_volume - position_volume > 1e-12:
            raise HTTPException(status_code=400, detail={"message": "close volume exceeds position volume", "position_volume": position_volume, "requested_volume": close_volume})

        sltp_cleanup: dict[str, Any] | None = None
        if req.remove_sltp_before_close and (pos.get("sl") or pos.get("tp")):
            cleanup_request = _build_sltp_request(
                mt5,
                pos,
                sl=0.0,
                tp=0.0,
                deviation=req.deviation,
                comment="mt5-proxy-preclose-remove-sltp",
            )
            sltp_cleanup = _send_order_direct(mt5, cleanup_request)
            if not sltp_cleanup.get("ok"):
                sltp_cleanup["message"] = "requested remove_sltp_before_close failed; close was not sent"
                return sltp_cleanup
            refreshed = _mt5_value(mt5, "positions_get", ticket=req.ticket)
            if refreshed:
                pos = refreshed[0]

        close_type = mt5.ORDER_TYPE_SELL if pos["type"] == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick_data["bid"] if pos["type"] == mt5.POSITION_TYPE_BUY else tick_data["ask"]
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": pos["ticket"],
            "symbol": pos["symbol"],
            "volume": close_volume,
            "type": close_type,
            "price": price,
            "deviation": req.deviation,
            "magic": req.magic,
            "comment": req.comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }

        payload = _send_order_with_filling_fallback(mt5, request, req.type_filling)
        payload["symbol_filling_mode"] = info.get("filling_mode")
        payload["symbol_trade_exemode"] = info.get("trade_exemode")
        payload["position_before_close"] = pos
        payload["close_volume"] = close_volume
        payload["sltp_cleanup"] = sltp_cleanup
        payload["sltp_lifecycle"] = (
            "full_close_removes_the_position_so_no_separate_sltp_cleanup_is_needed"
            if abs(close_volume - position_volume) <= 1e-12
            else "partial_close_leaves_the_position_open_so_its_position_sltp_remains_until_modified_or_removed"
        )
        if req.verify:
            payload["position_after_close"] = _mt5_value(mt5, "positions_get", ticket=req.ticket)
        return payload


@app.post("/v1/positions/{ticket}/sltp", dependencies=[Depends(_api_key_guard)])
def set_sltp(ticket: int, req: SetSltpRequest):
    _require_trading_enabled()
    with _mt5_session() as mt5:
        pos_list = _mt5_value(mt5, "positions_get", ticket=ticket)
        if not pos_list:
            raise HTTPException(status_code=404, detail="position not found")
        pos = pos_list[0]
        request = _build_sltp_request(
            mt5,
            pos,
            sl=0.0 if req.sl is None else req.sl,
            tp=0.0 if req.tp is None else req.tp,
            deviation=req.deviation,
            comment=req.comment,
        )
        return _send_order_direct(mt5, request)


@app.delete("/v1/positions/{ticket}/sltp", dependencies=[Depends(_api_key_guard)])
def remove_sltp(ticket: int, remove_sl: bool = True, remove_tp: bool = True, deviation: int = 30):
    _require_trading_enabled()
    with _mt5_session() as mt5:
        pos_list = _mt5_value(mt5, "positions_get", ticket=ticket)
        if not pos_list:
            raise HTTPException(status_code=404, detail="position not found")
        pos = pos_list[0]
        request = _build_sltp_request(
            mt5,
            pos,
            sl=0.0 if remove_sl else pos["sl"],
            tp=0.0 if remove_tp else pos["tp"],
            deviation=deviation,
            comment="mt5-proxy-remove-sltp",
        )
        return _send_order_direct(mt5, request)


@app.post("/v1/orders/pending", dependencies=[Depends(_api_key_guard)])
def place_pending_order(req: PendingOrderRequest):
    """
    Place a pending order with SL/TP. When MT5 triggers the pending order, the resulting
    position receives these SL/TP values from the order; they are not separate proxy-owned orders.
    """
    _require_trading_enabled()
    with _mt5_session() as mt5:
        _select_symbol(mt5, req.symbol)
        info = _mt5_value(mt5, "symbol_info", req.symbol)
        order_type = _pending_order_type(mt5, req.side, req.order_kind)
        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": req.symbol,
            "volume": req.volume,
            "type": order_type,
            "price": req.price,
            "deviation": req.deviation,
            "magic": req.magic,
            "comment": req.comment,
            "type_time": _order_time_value(mt5, req.type_time),
        }
        if req.order_kind == "stop_limit":
            if req.stoplimit is None:
                raise HTTPException(status_code=400, detail="stoplimit is required for stop_limit pending orders")
            request["stoplimit"] = req.stoplimit
        elif req.stoplimit is not None:
            request["stoplimit"] = req.stoplimit
        if req.sl is not None:
            request["sl"] = req.sl
        if req.tp is not None:
            request["tp"] = req.tp
        _apply_expiration(request, req.expiration)

        payload = _send_order_with_filling_fallback(mt5, request, req.type_filling)
        payload["symbol_filling_mode"] = info.get("filling_mode")
        payload["symbol_trade_exemode"] = info.get("trade_exemode")
        payload["pending_order_flow"] = "pending_order_waits_until_triggered_then_opens_a_position_with_the_specified_sltp"
        return payload


@app.post("/v1/orders/{ticket}/modify", dependencies=[Depends(_api_key_guard)])
def modify_pending_order(ticket: int, req: ModifyPendingOrderRequest):
    """Modify a still-pending order: trigger price, stop-limit price, SL/TP, and expiration."""
    _require_trading_enabled()
    with _mt5_session() as mt5:
        order_list = _mt5_value(mt5, "orders_get", ticket=ticket)
        if not order_list:
            raise HTTPException(status_code=404, detail="pending order not found")
        order = order_list[0]
        request = {
            "action": mt5.TRADE_ACTION_MODIFY,
            "order": ticket,
            "symbol": order.get("symbol"),
            "price": req.price if req.price is not None else order.get("price_open"),
            "sl": 0.0 if req.remove_sl else (req.sl if req.sl is not None else order.get("sl", 0.0)),
            "tp": 0.0 if req.remove_tp else (req.tp if req.tp is not None else order.get("tp", 0.0)),
            "deviation": req.deviation,
            "comment": req.comment,
        }
        stoplimit = req.stoplimit if req.stoplimit is not None else order.get("price_stoplimit")
        if stoplimit:
            request["stoplimit"] = stoplimit
        if req.type_time is not None:
            request["type_time"] = _order_time_value(mt5, req.type_time)
        elif order.get("type_time") is not None:
            request["type_time"] = order.get("type_time")
        _apply_expiration(request, req.expiration)

        payload = _send_order_direct(mt5, request)
        payload["order_before_modify"] = order
        if payload.get("ok"):
            payload["order_after_modify"] = _mt5_value(mt5, "orders_get", ticket=ticket)
        return payload


@app.delete("/v1/orders/{ticket}", dependencies=[Depends(_api_key_guard)])
def remove_pending_order(ticket: int, comment: str = "mt5-proxy-remove-pending"):
    """Cancel a pending order. This does not close positions that may have already been triggered."""
    _require_trading_enabled()
    with _mt5_session() as mt5:
        order_list = _mt5_value(mt5, "orders_get", ticket=ticket)
        if not order_list:
            raise HTTPException(status_code=404, detail="pending order not found")
        order = order_list[0]
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
            "symbol": order.get("symbol"),
            "comment": comment,
        }
        payload = _send_order_direct(mt5, request)
        payload["order_before_remove"] = order
        if payload.get("ok"):
            payload["order_after_remove"] = _mt5_value(mt5, "orders_get", ticket=ticket)
        return payload
