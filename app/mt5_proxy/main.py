from __future__ import annotations

import os
import socket
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

APP_VERSION = "0.3.0"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _api_key_guard(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("API_KEY", "dev-api-key")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid API key")


def _asdict(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
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


def _rates_to_rows(rates: Any) -> list[dict[str, Any]]:
    if rates is None:
        return []
    rows: list[dict[str, Any]] = []
    names = getattr(getattr(rates, "dtype", None), "names", None)
    if names:
        for r in rates:
            item = {name: _asdict(r[name]) for name in names}
            if "time" in item:
                item["time_iso"] = datetime.fromtimestamp(int(item["time"]), tz=timezone.utc).isoformat()
            rows.append(item)
        return rows
    for r in rates:
        rows.append(_asdict(r))
    return rows


def _parse_dt(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _bridge_endpoint() -> tuple[str, int]:
    return os.getenv("MT5LINUX_HOST", "127.0.0.1"), int(os.getenv("MT5LINUX_PORT", "8001"))


def _tcp_open(host: str, port: int, timeout_sec: float = 1.0) -> tuple[bool, str | None]:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True, None
    except OSError as exc:
        return False, str(exc)


def _connect_mt5():
    try:
        from mt5linux import MetaTrader5
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"mt5linux import failed: {exc}") from exc

    host, port = _bridge_endpoint()
    retries = max(1, int(os.getenv("MT5_CONNECT_RETRIES", "3")))
    delay = max(0.0, float(os.getenv("MT5_CONNECT_RETRY_DELAY", "2")))
    timeout = int(os.getenv("MT5LINUX_TIMEOUT", "300"))
    init_timeout = int(os.getenv("MT5_TIMEOUT_MS", "60000"))
    last_detail: Any = None

    for attempt in range(1, retries + 1):
        mt5 = None
        initialized = False
        try:
            mt5 = MetaTrader5(host=host, port=port, timeout=timeout)
            init_kwargs: dict[str, Any] = {"timeout": init_timeout}
            if os.getenv("MT5_LOGIN"):
                init_kwargs["login"] = int(os.environ["MT5_LOGIN"])
                init_kwargs["password"] = os.getenv("MT5_PASSWORD", "")
                init_kwargs["server"] = os.getenv("MT5_SERVER", "")

            initialized = bool(mt5.initialize(**init_kwargs))
            if initialized:
                return mt5
            last_detail = {"message": "mt5.initialize failed", "last_error": _asdict(mt5.last_error()), "attempt": attempt}
        except Exception as exc:
            last_detail = {"message": f"Cannot connect to mt5linux bridge at {host}:{port}", "error": str(exc), "attempt": attempt}
        finally:
            if mt5 is not None and not initialized:
                try:
                    mt5.shutdown()
                except Exception:
                    pass
        if attempt < retries:
            time.sleep(delay)

    raise HTTPException(status_code=503, detail=last_detail)


class OpenDealRequest(BaseModel):
    symbol: str = "EURUSD"
    side: str = Field(pattern="^(buy|sell)$")
    volume: float = 0.01
    sl: Optional[float] = None
    tp: Optional[float] = None
    deviation: int = 30
    magic: int = 424242
    comment: str = "mt5-proxy-open"
    type_filling: str = "IOC"  # IOC, FOK, RETURN


class CloseDealRequest(BaseModel):
    ticket: int
    deviation: int = 30
    magic: int = 424242
    comment: str = "mt5-proxy-close"


class SetSltpRequest(BaseModel):
    sl: Optional[float] = None
    tp: Optional[float] = None
    deviation: int = 30
    comment: str = "mt5-proxy-sltp"


app = FastAPI(title="MT5 Wine Proxy", version=APP_VERSION)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "mt5-wine-proxy",
        "version": APP_VERSION,
        "time": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    }


@app.get("/ready")
def ready(
    deep: bool = Query(False, description="When true, initialize MT5 through the bridge."),
    x_api_key: str | None = Header(default=None),
):
    if deep:
        _api_key_guard(x_api_key)
    host, port = _bridge_endpoint()
    bridge_open, bridge_error = _tcp_open(host, port)
    payload: dict[str, Any] = {
        "ok": bridge_open,
        "service": "mt5-wine-proxy",
        "bridge": {"host": host, "port": port, "tcp_open": bridge_open, "error": bridge_error},
        "deep": deep,
    }
    if not bridge_open:
        raise HTTPException(status_code=503, detail=payload)
    if not deep:
        return payload

    mt5 = _connect_mt5()
    try:
        account = mt5.account_info()
        payload.update(
            {
                "ok": account is not None,
                "version_info": _asdict(mt5.version()),
                "terminal_info": _asdict(mt5.terminal_info()),
                "account": _asdict(account),
                "last_error": _asdict(mt5.last_error()),
            }
        )
        if account is None:
            raise HTTPException(status_code=503, detail=payload)
        return payload
    finally:
        mt5.shutdown()


@app.get("/v1/bridge", dependencies=[Depends(_api_key_guard)])
def bridge_status():
    mt5 = _connect_mt5()
    try:
        return {
            "version": _asdict(mt5.version()),
            "terminal_info": _asdict(mt5.terminal_info()),
            "last_error": _asdict(mt5.last_error()),
        }
    finally:
        mt5.shutdown()


@app.get("/v1/account", dependencies=[Depends(_api_key_guard)])
def account_info():
    mt5 = _connect_mt5()
    try:
        return {"account": _asdict(mt5.account_info()), "last_error": _asdict(mt5.last_error())}
    finally:
        mt5.shutdown()


@app.get("/v1/symbols/{symbol}/tick", dependencies=[Depends(_api_key_guard)])
def tick(symbol: str):
    mt5 = _connect_mt5()
    try:
        mt5.symbol_select(symbol, True)
        return {
            "symbol": symbol,
            "symbol_info": _asdict(mt5.symbol_info(symbol)),
            "tick": _asdict(mt5.symbol_info_tick(symbol)),
            "last_error": _asdict(mt5.last_error()),
        }
    finally:
        mt5.shutdown()


@app.get("/v1/bars", dependencies=[Depends(_api_key_guard)])
def bars(
    symbol: str = Query(...),
    timeframe: str = Query("M1"),
    start: str = Query(..., description="UTC ISO time, e.g. 2026-06-16T08:00:00Z"),
    end: str = Query(..., description="UTC ISO time"),
):
    mt5 = _connect_mt5()
    try:
        tf_name = f"TIMEFRAME_{timeframe.upper()}"
        if not hasattr(mt5, tf_name):
            raise HTTPException(status_code=400, detail=f"unknown timeframe {timeframe}")
        tf = getattr(mt5, tf_name)
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_range(symbol, tf, _parse_dt(start), _parse_dt(end))
        return {"symbol": symbol, "timeframe": timeframe, "bars": _rates_to_rows(rates), "last_error": _asdict(mt5.last_error())}
    finally:
        mt5.shutdown()


@app.get("/v1/positions", dependencies=[Depends(_api_key_guard)])
def positions(symbol: str | None = None):
    mt5 = _connect_mt5()
    try:
        data = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        return {"positions": _asdict(data) or [], "last_error": _asdict(mt5.last_error())}
    finally:
        mt5.shutdown()


@app.post("/v1/deals/open", dependencies=[Depends(_api_key_guard)])
def open_deal(req: OpenDealRequest):
    if not _env_bool("TRADING_ENABLED", False):
        raise HTTPException(status_code=403, detail="TRADING_ENABLED=false")
    mt5 = _connect_mt5()
    try:
        mt5.symbol_select(req.symbol, True)
        info = mt5.symbol_info(req.symbol)
        tick = mt5.symbol_info_tick(req.symbol)
        if info is None or tick is None:
            raise HTTPException(status_code=400, detail={"message": "symbol not available", "last_error": _asdict(mt5.last_error())})
        side_buy = req.side.lower() == "buy"
        filling_map = {"IOC": mt5.ORDER_FILLING_IOC, "FOK": mt5.ORDER_FILLING_FOK, "RETURN": mt5.ORDER_FILLING_RETURN}
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": req.symbol,
            "volume": req.volume,
            "type": mt5.ORDER_TYPE_BUY if side_buy else mt5.ORDER_TYPE_SELL,
            "price": tick.ask if side_buy else tick.bid,
            "deviation": req.deviation,
            "magic": req.magic,
            "comment": req.comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_map.get(req.type_filling.upper(), mt5.ORDER_FILLING_IOC),
        }
        if req.sl is not None:
            request["sl"] = req.sl
        if req.tp is not None:
            request["tp"] = req.tp
        result = mt5.order_send(request)
        return {"request": request, "result": _asdict(result), "last_error": _asdict(mt5.last_error())}
    finally:
        mt5.shutdown()


@app.post("/v1/deals/close", dependencies=[Depends(_api_key_guard)])
def close_deal(req: CloseDealRequest):
    if not _env_bool("TRADING_ENABLED", False):
        raise HTTPException(status_code=403, detail="TRADING_ENABLED=false")
    mt5 = _connect_mt5()
    try:
        pos_list = mt5.positions_get(ticket=req.ticket)
        if not pos_list:
            raise HTTPException(status_code=404, detail="position not found")
        pos = pos_list[0]
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            raise HTTPException(status_code=400, detail={"message": "tick unavailable", "last_error": _asdict(mt5.last_error())})
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": pos.ticket,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "price": price,
            "deviation": req.deviation,
            "magic": req.magic,
            "comment": req.comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        return {"request": request, "result": _asdict(result), "last_error": _asdict(mt5.last_error())}
    finally:
        mt5.shutdown()


@app.post("/v1/positions/{ticket}/sltp", dependencies=[Depends(_api_key_guard)])
def set_sltp(ticket: int, req: SetSltpRequest):
    if not _env_bool("TRADING_ENABLED", False):
        raise HTTPException(status_code=403, detail="TRADING_ENABLED=false")
    mt5 = _connect_mt5()
    try:
        pos_list = mt5.positions_get(ticket=ticket)
        if not pos_list:
            raise HTTPException(status_code=404, detail="position not found")
        pos = pos_list[0]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": pos.symbol,
            "sl": 0.0 if req.sl is None else req.sl,
            "tp": 0.0 if req.tp is None else req.tp,
            "deviation": req.deviation,
            "comment": req.comment,
        }
        result = mt5.order_send(request)
        return {"request": request, "result": _asdict(result), "last_error": _asdict(mt5.last_error())}
    finally:
        mt5.shutdown()


@app.delete("/v1/positions/{ticket}/sltp", dependencies=[Depends(_api_key_guard)])
def remove_sltp(ticket: int, remove_sl: bool = True, remove_tp: bool = True, deviation: int = 30):
    if not _env_bool("TRADING_ENABLED", False):
        raise HTTPException(status_code=403, detail="TRADING_ENABLED=false")
    mt5 = _connect_mt5()
    try:
        pos_list = mt5.positions_get(ticket=ticket)
        if not pos_list:
            raise HTTPException(status_code=404, detail="position not found")
        pos = pos_list[0]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": pos.symbol,
            "sl": 0.0 if remove_sl else pos.sl,
            "tp": 0.0 if remove_tp else pos.tp,
            "deviation": deviation,
            "comment": "mt5-proxy-remove-sltp",
        }
        result = mt5.order_send(request)
        return {"request": request, "result": _asdict(result), "last_error": _asdict(mt5.last_error())}
    finally:
        mt5.shutdown()
