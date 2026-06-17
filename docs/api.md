# MT5 Wine Proxy API

Base URL:

```python
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "dev-api-key"
HEADERS = {"X-API-Key": API_KEY}
```

Most `/v1/*` endpoints require:

```http
X-API-Key: dev-api-key
```

Trading endpoints also require:

```bash
TRADING_ENABLED=true
```

Common response fields:

```json
{
  "ok": true,
  "empty": false,
  "last_error": [1, "Success"]
}
```

Trade response success retcodes:

```text
10008 = order placed
10009 = request done
10010 = done partially
```

## Concepts

`side` is the intended position direction: `buy` or `sell`.

`order_kind` is the pending-order trigger style: `limit`, `stop`, or `stop_limit`.

Mapping:

```text
buy  + limit      = BUY_LIMIT
sell + limit      = SELL_LIMIT
buy  + stop       = BUY_STOP
sell + stop       = SELL_STOP
buy  + stop_limit = BUY_STOP_LIMIT
sell + stop_limit = SELL_STOP_LIMIT
```

Full market close removes the position, so position-attached SL/TP does not need a separate cleanup call. Partial close leaves the remaining position open, so its SL/TP remains until modified or removed.

---

# Health

## GET /health

Checks whether the API process is alive. No API key required.

Request:

```http
GET /health
```

Response:

```json
{
  "ok": true,
  "service": "mt5-wine-proxy"
}
```

Python:

```python
import requests

resp = requests.get(f"{BASE_URL}/health")
print(resp.status_code, resp.json())
```

## GET /health/live

Liveness probe. No API key required.

Request:

```http
GET /health/live
```

Response:

```json
{
  "ok": true,
  "service": "mt5-wine-proxy"
}
```

Python:

```python
resp = requests.get(f"{BASE_URL}/health/live")
print(resp.status_code, resp.json())
```

## GET /health/ready

Readiness probe. Checks whether the mt5linux bridge is listening and MT5 can initialize.

Request:

```http
GET /health/ready
```

Response:

```json
{
  "ok": true,
  "service": "mt5-wine-proxy",
  "bridge": {
    "host": "127.0.0.1",
    "port": 8001,
    "listening": true,
    "initialize": true
  },
  "version": [500, 5836, "28 Apr 2026"],
  "terminal_info": {
    "connected": true,
    "trade_allowed": true,
    "tradeapi_disabled": false
  },
  "empty": false,
  "last_error": [1, "Success"]
}
```

Python:

```python
resp = requests.get(f"{BASE_URL}/health/ready")
print(resp.status_code, resp.json())
```

---

# Status and account

## GET /v1/bridge

Returns MT5 bridge and terminal information.

Request:

```http
GET /v1/bridge
```

Response:

```json
{
  "ok": true,
  "version": [500, 5836, "28 Apr 2026"],
  "terminal_info": {
    "connected": true,
    "trade_allowed": true,
    "tradeapi_disabled": false
  },
  "empty": false,
  "last_error": [1, "Success"]
}
```

Python:

```python
resp = requests.get(f"{BASE_URL}/v1/bridge", headers=HEADERS)
print(resp.status_code, resp.json())
```

## GET /v1/status

Returns compact terminal, account, trading, and count status.

Request:

```http
GET /v1/status
```

Response:

```json
{
  "ok": true,
  "empty": false,
  "version": [500, 5836, "28 Apr 2026"],
  "terminal_info": {
    "connected": true,
    "trade_allowed": true,
    "tradeapi_disabled": false
  },
  "account": {
    "login": 108444014,
    "server": "MetaQuotes-Demo",
    "balance": 99999.89,
    "equity": 99999.89,
    "trade_allowed": true,
    "trade_expert": true
  },
  "trading": {
    "proxy_enabled": true,
    "terminal_trade_allowed": true,
    "terminal_tradeapi_disabled": false,
    "account_trade_allowed": true,
    "account_trade_expert": true
  },
  "counts": {
    "symbols": 11815,
    "orders": 0,
    "positions": 0
  },
  "last_error": [1, "Success"]
}
```

Python:

```python
resp = requests.get(f"{BASE_URL}/v1/status", headers=HEADERS)
print(resp.status_code, resp.json())
```

## GET /v1/account

Returns MT5 account information.

Request:

```http
GET /v1/account
```

Response:

```json
{
  "ok": true,
  "empty": false,
  "account": {
    "login": 108444014,
    "server": "MetaQuotes-Demo",
    "currency": "USD",
    "balance": 99999.89,
    "equity": 99999.92,
    "margin": 46.4,
    "margin_free": 99953.52,
    "profit": 0.03,
    "trade_allowed": true,
    "trade_expert": true
  },
  "last_error": [1, "Success"]
}
```

Python:

```python
resp = requests.get(f"{BASE_URL}/v1/account", headers=HEADERS)
print(resp.status_code, resp.json())
```

---

# Market data

## GET /v1/symbols/{symbol}/tick

Returns symbol metadata and latest tick.

Request:

```http
GET /v1/symbols/EURUSD/tick
```

Response:

```json
{
  "ok": true,
  "empty": false,
  "symbol": "EURUSD",
  "symbol_info": {
    "name": "EURUSD",
    "description": "Euro vs US Dollar",
    "digits": 5,
    "point": 0.00001,
    "volume_min": 0.01,
    "volume_step": 0.01,
    "trade_mode": 4,
    "filling_mode": 1
  },
  "tick": {
    "bid": 1.15991,
    "ask": 1.15991,
    "time": 1781695476,
    "time_msc": 1781695476578
  },
  "last_error": [1, "Success"]
}
```

Python:

```python
symbol = "EURUSD"

resp = requests.get(f"{BASE_URL}/v1/symbols/{symbol}/tick", headers=HEADERS)
print(resp.status_code, resp.json())
```

## GET /v1/bars

Returns OHLC bars for a symbol and timeframe.

Query params:

```text
symbol: required, e.g. EURUSD
timeframe: default M1
start: UTC ISO datetime
end: UTC ISO datetime
```

Request:

```http
GET /v1/bars?symbol=EURUSD&timeframe=M1&start=2026-06-17T06:00:00Z&end=2026-06-17T08:00:00Z
```

Response:

```json
{
  "ok": true,
  "empty": false,
  "symbol": "EURUSD",
  "timeframe": "M1",
  "bars": [
    {
      "time": 1781677020,
      "time_iso": "2026-06-17T06:17:00+00:00",
      "open": 1.16098,
      "high": 1.161,
      "low": 1.16091,
      "close": 1.16093,
      "tick_volume": 63,
      "spread": 0,
      "real_volume": 0
    }
  ],
  "last_error": [1, "Success"]
}
```

Python:

```python
params = {
    "symbol": "EURUSD",
    "timeframe": "M1",
    "start": "2026-06-17T06:00:00Z",
    "end": "2026-06-17T08:00:00Z",
}

resp = requests.get(f"{BASE_URL}/v1/bars", headers=HEADERS, params=params)
print(resp.status_code, resp.json())
```

---

# Read positions and orders

## GET /v1/positions

Returns open positions. Filter by `symbol` or `ticket`.

Request:

```http
GET /v1/positions?symbol=EURUSD
```

Response:

```json
{
  "ok": true,
  "empty": false,
  "positions": [
    {
      "ticket": 9126287001,
      "symbol": "EURUSD",
      "type": 0,
      "volume": 0.01,
      "price_open": 1.16024,
      "price_current": 1.16050,
      "sl": 1.15923,
      "tp": 1.16223,
      "profit": 0.26,
      "magic": 13,
      "comment": "mt5-proxy-open"
    }
  ],
  "last_error": [1, "Success"]
}
```

Python:

```python
params = {"symbol": "EURUSD"}
resp = requests.get(f"{BASE_URL}/v1/positions", headers=HEADERS, params=params)
print(resp.status_code, resp.json())
```

Get one position by ticket:

```python
params = {"ticket": 9126287001}
resp = requests.get(f"{BASE_URL}/v1/positions", headers=HEADERS, params=params)
print(resp.status_code, resp.json())
```

## GET /v1/orders

Returns pending orders. Filter by `symbol` or `ticket`.

Request:

```http
GET /v1/orders?symbol=EURUSD
```

Response:

```json
{
  "ok": true,
  "empty": false,
  "orders": [
    {
      "ticket": 9126652220,
      "symbol": "EURUSD",
      "type": 2,
      "volume_initial": 0.01,
      "price_open": 1.16016,
      "sl": 1.15725,
      "tp": 1.16025,
      "magic": 19,
      "comment": "mt5-proxy-pending"
    }
  ],
  "last_error": [1, "Success"]
}
```

Python:

```python
params = {"symbol": "EURUSD"}
resp = requests.get(f"{BASE_URL}/v1/orders", headers=HEADERS, params=params)
print(resp.status_code, resp.json())
```

Get one pending order by ticket:

```python
params = {"ticket": 9126652220}
resp = requests.get(f"{BASE_URL}/v1/orders", headers=HEADERS, params=params)
print(resp.status_code, resp.json())
```

---

# Generic read-only MT5 call

## POST /v1/mt5/call/{method}

Read-only escape hatch for exposed MT5 methods. `order_send` is not exposed here.

Request:

```http
POST /v1/mt5/call/positions_get
```

Request JSON:

```json
{
  "kwargs": {
    "symbol": "EURUSD"
  }
}
```

Response:

```json
{
  "ok": true,
  "method": "positions_get",
  "empty": false,
  "result": [
    {
      "ticket": 9126287001,
      "symbol": "EURUSD",
      "volume": 0.01,
      "sl": 1.15923,
      "tp": 1.16223
    }
  ],
  "last_error": [1, "Success"]
}
```

Python:

```python
body = {
    "kwargs": {
        "symbol": "EURUSD"
    }
}

resp = requests.post(
    f"{BASE_URL}/v1/mt5/call/positions_get",
    headers=HEADERS,
    json=body,
)
print(resp.status_code, resp.json())
```

Datetime and MT5 constants are supported:

```python
body = {
    "args": [
        "EURUSD",
        "MT5:TIMEFRAME_M1",
        "2026-06-17T06:00:00Z",
        "2026-06-17T08:00:00Z"
    ]
}

resp = requests.post(
    f"{BASE_URL}/v1/mt5/call/copy_rates_range",
    headers=HEADERS,
    json=body,
)
print(resp.status_code, resp.json())
```

---

# Market deals

## POST /v1/deals/open

Opens a market position. Optional `sl` and `tp` are attached to the position.

Request:

```http
POST /v1/deals/open
```

Request JSON:

```json
{
  "symbol": "EURUSD",
  "side": "buy",
  "volume": 0.01,
  "sl": 1.15923,
  "tp": 1.16223,
  "deviation": 30,
  "magic": 13,
  "comment": "mt5-proxy-open",
  "type_filling": "AUTO"
}
```

Response:

```json
{
  "ok": true,
  "method": "order_send",
  "retcode": 10009,
  "empty": false,
  "request": {
    "action": 1,
    "symbol": "EURUSD",
    "volume": 0.01,
    "type": 0,
    "price": 1.16023,
    "sl": 1.15923,
    "tp": 1.16223,
    "deviation": 30,
    "magic": 13,
    "comment": "mt5-proxy-open"
  },
  "result": {
    "retcode": 10009,
    "comment": "Request executed",
    "deal": 8761080131,
    "order": 9126287001,
    "price": 1.16024,
    "volume": 0.01
  },
  "filling_attempts": [
    {
      "type_filling_name": "FOK",
      "retcode": 10009,
      "comment": "Request executed"
    }
  ],
  "symbol_filling_mode": 1,
  "symbol_trade_exemode": 2,
  "last_error": [1, "Success"]
}
```

Python:

```python
body = {
    "symbol": "EURUSD",
    "side": "buy",
    "volume": 0.01,
    "sl": 1.15923,
    "tp": 1.16223,
    "magic": 13,
    "type_filling": "AUTO",
}

resp = requests.post(f"{BASE_URL}/v1/deals/open", headers=HEADERS, json=body)
print(resp.status_code, resp.json())
```

## POST /v1/deals/close

Closes a position by ticket. If `volume` is omitted, the full position volume is closed.

Request:

```http
POST /v1/deals/close
```

Request JSON:

```json
{
  "ticket": 9126287001,
  "volume": 0.01,
  "deviation": 30,
  "magic": 13,
  "type_filling": "AUTO",
  "comment": "mt5-proxy-close",
  "remove_sltp_before_close": false,
  "verify": true
}
```

Response:

```json
{
  "ok": true,
  "method": "order_send",
  "retcode": 10009,
  "close_volume": 0.01,
  "position_before_close": {
    "ticket": 9126287001,
    "symbol": "EURUSD",
    "volume": 0.01,
    "sl": 1.15923,
    "tp": 1.16223
  },
  "position_after_close": [],
  "sltp_cleanup": null,
  "sltp_lifecycle": "full_close_removes_the_position_so_no_separate_sltp_cleanup_is_needed",
  "request": {
    "action": 1,
    "position": 9126287001,
    "symbol": "EURUSD",
    "volume": 0.01,
    "type": 1,
    "price": 1.16046,
    "deviation": 30,
    "magic": 13,
    "comment": "mt5-proxy-close"
  },
  "result": {
    "retcode": 10009,
    "comment": "Request executed",
    "deal": 8761252875,
    "order": 9126452357,
    "price": 1.16046,
    "volume": 0.01
  },
  "last_error": [1, "Success"]
}
```

Python:

```python
body = {
    "ticket": 9126287001,
    "magic": 13,
    "type_filling": "AUTO",
    "remove_sltp_before_close": False,
    "verify": True,
}

resp = requests.post(f"{BASE_URL}/v1/deals/close", headers=HEADERS, json=body)
print(resp.status_code, resp.json())
```

Use explicit SL/TP cleanup before close:

```python
body = {
    "ticket": 9126287001,
    "remove_sltp_before_close": True,
    "verify": True,
}

resp = requests.post(f"{BASE_URL}/v1/deals/close", headers=HEADERS, json=body)
print(resp.status_code, resp.json())
```

---

# Position SL/TP

## POST /v1/positions/{ticket}/sltp

Sets or updates SL/TP on an open position. Passing `null` removes that side because the proxy sends `0.0`.

Request:

```http
POST /v1/positions/9126287001/sltp
```

Request JSON:

```json
{
  "sl": 1.15950,
  "tp": 1.16200,
  "deviation": 30,
  "comment": "mt5-proxy-sltp"
}
```

Response:

```json
{
  "ok": true,
  "method": "order_send",
  "retcode": 10009,
  "request": {
    "action": 6,
    "position": 9126287001,
    "symbol": "EURUSD",
    "sl": 1.15950,
    "tp": 1.16200,
    "deviation": 30,
    "comment": "mt5-proxy-sltp"
  },
  "result": {
    "retcode": 10009,
    "comment": "Request executed"
  },
  "last_error": [1, "Success"]
}
```

Python:

```python
ticket = 9126287001
body = {
    "sl": 1.15950,
    "tp": 1.16200,
}

resp = requests.post(
    f"{BASE_URL}/v1/positions/{ticket}/sltp",
    headers=HEADERS,
    json=body,
)
print(resp.status_code, resp.json())
```

## DELETE /v1/positions/{ticket}/sltp

Removes SL and/or TP from an open position.

Query params:

```text
remove_sl: default true
remove_tp: default true
deviation: default 30
```

Request:

```http
DELETE /v1/positions/9126287001/sltp?remove_sl=true&remove_tp=true
```

Response:

```json
{
  "ok": true,
  "method": "order_send",
  "retcode": 10009,
  "request": {
    "action": 6,
    "position": 9126287001,
    "symbol": "EURUSD",
    "sl": 0.0,
    "tp": 0.0,
    "deviation": 30,
    "comment": "mt5-proxy-remove-sltp"
  },
  "result": {
    "retcode": 10009,
    "comment": "Request executed"
  },
  "last_error": [1, "Success"]
}
```

Python:

```python
ticket = 9126287001
params = {
    "remove_sl": True,
    "remove_tp": True,
}

resp = requests.delete(
    f"{BASE_URL}/v1/positions/{ticket}/sltp",
    headers=HEADERS,
    params=params,
)
print(resp.status_code, resp.json())
```

---

# Pending orders

## POST /v1/orders/pending

Places a pending order. When triggered, MT5 opens a position in the requested `side` with the given SL/TP.

Request:

```http
POST /v1/orders/pending
```

Request JSON:

```json
{
  "symbol": "EURUSD",
  "side": "buy",
  "order_kind": "limit",
  "volume": 0.01,
  "price": 1.16016,
  "sl": 1.15725,
  "tp": 1.16225,
  "deviation": 30,
  "magic": 19,
  "comment": "mt5-proxy-pending",
  "type_time": "GTC",
  "expiration": null,
  "type_filling": "AUTO"
}
```

For `order_kind = stop_limit`, also provide:

```json
{
  "stoplimit": 1.16000
}
```

Response:

```json
{
  "ok": true,
  "method": "order_send",
  "retcode": 10009,
  "pending_order_flow": "pending_order_waits_until_triggered_then_opens_a_position_with_the_specified_sltp",
  "request": {
    "action": 5,
    "symbol": "EURUSD",
    "volume": 0.01,
    "type": 2,
    "price": 1.16016,
    "sl": 1.15725,
    "tp": 1.16225,
    "magic": 19,
    "comment": "mt5-proxy-pending"
  },
  "result": {
    "retcode": 10009,
    "comment": "Request executed",
    "order": 9126652220,
    "deal": 0
  },
  "last_error": [1, "Success"]
}
```

Python:

```python
body = {
    "symbol": "EURUSD",
    "side": "buy",
    "order_kind": "limit",
    "volume": 0.01,
    "price": 1.16016,
    "sl": 1.15725,
    "tp": 1.16225,
    "magic": 19,
    "type_filling": "AUTO",
}

resp = requests.post(f"{BASE_URL}/v1/orders/pending", headers=HEADERS, json=body)
print(resp.status_code, resp.json())
```

## POST /v1/orders/{ticket}/modify

Modifies a still-pending order.

Request:

```http
POST /v1/orders/9126652220/modify
```

Request JSON:

```json
{
  "price": 1.16000,
  "sl": 1.15700,
  "tp": 1.16200,
  "remove_sl": false,
  "remove_tp": false,
  "deviation": 30,
  "comment": "mt5-proxy-modify-pending"
}
```

Response:

```json
{
  "ok": true,
  "method": "order_send",
  "retcode": 10009,
  "order_before_modify": {
    "ticket": 9126652220,
    "symbol": "EURUSD",
    "price_open": 1.16016,
    "sl": 1.15725,
    "tp": 1.16225
  },
  "order_after_modify": [
    {
      "ticket": 9126652220,
      "symbol": "EURUSD",
      "price_open": 1.16000,
      "sl": 1.15700,
      "tp": 1.16200
    }
  ],
  "last_error": [1, "Success"]
}
```

Python:

```python
ticket = 9126652220
body = {
    "price": 1.16000,
    "sl": 1.15700,
    "tp": 1.16200,
}

resp = requests.post(
    f"{BASE_URL}/v1/orders/{ticket}/modify",
    headers=HEADERS,
    json=body,
)
print(resp.status_code, resp.json())
```

Remove only SL or TP from a pending order:

```python
body = {
    "remove_sl": True,
    "remove_tp": False,
}

resp = requests.post(
    f"{BASE_URL}/v1/orders/{ticket}/modify",
    headers=HEADERS,
    json=body,
)
print(resp.status_code, resp.json())
```

## DELETE /v1/orders/{ticket}

Cancels a pending order. This does not close any position that may already have been triggered.

Request:

```http
DELETE /v1/orders/9126652220
```

Optional query param:

```text
comment: default mt5-proxy-remove-pending
```

Response:

```json
{
  "ok": true,
  "method": "order_send",
  "retcode": 10009,
  "order_before_remove": {
    "ticket": 9126652220,
    "symbol": "EURUSD",
    "price_open": 1.16016,
    "sl": 1.15725,
    "tp": 1.16225
  },
  "order_after_remove": [],
  "last_error": [1, "Success"]
}
```

Python:

```python
ticket = 9126652220

resp = requests.delete(
    f"{BASE_URL}/v1/orders/{ticket}",
    headers=HEADERS,
)
print(resp.status_code, resp.json())
```

---

# Typical flows

## Open market position with SL/TP, then close

```python
open_body = {
    "symbol": "EURUSD",
    "side": "buy",
    "volume": 0.01,
    "sl": 1.15923,
    "tp": 1.16223,
    "type_filling": "AUTO",
}

opened = requests.post(
    f"{BASE_URL}/v1/deals/open",
    headers=HEADERS,
    json=open_body,
).json()

position_ticket = opened["result"]["order"]

close_body = {
    "ticket": position_ticket,
    "type_filling": "AUTO",
    "verify": True,
}

closed = requests.post(
    f"{BASE_URL}/v1/deals/close",
    headers=HEADERS,
    json=close_body,
).json()

print(opened)
print(closed)
```

## Open market position, remove SL/TP, then close

```python
ticket = 9126287001

requests.delete(
    f"{BASE_URL}/v1/positions/{ticket}/sltp",
    headers=HEADERS,
    params={"remove_sl": True, "remove_tp": True},
)

close_body = {
    "ticket": ticket,
    "verify": True,
}

resp = requests.post(
    f"{BASE_URL}/v1/deals/close",
    headers=HEADERS,
    json=close_body,
)
print(resp.status_code, resp.json())
```

## Place, modify, and cancel pending order

```python
place_body = {
    "symbol": "EURUSD",
    "side": "buy",
    "order_kind": "limit",
    "volume": 0.01,
    "price": 1.16016,
    "sl": 1.15725,
    "tp": 1.16225,
    "type_filling": "AUTO",
}

placed = requests.post(
    f"{BASE_URL}/v1/orders/pending",
    headers=HEADERS,
    json=place_body,
).json()

ticket = placed["result"]["order"]

modify_body = {
    "price": 1.16000,
    "sl": 1.15700,
    "tp": 1.16200,
}

modified = requests.post(
    f"{BASE_URL}/v1/orders/{ticket}/modify",
    headers=HEADERS,
    json=modify_body,
).json()

removed = requests.delete(
    f"{BASE_URL}/v1/orders/{ticket}",
    headers=HEADERS,
).json()

print(placed)
print(modified)
print(removed)
```

---

# Errors

Invalid API key:

```json
{
  "detail": "invalid API key"
}
```

Trading disabled:

```json
{
  "detail": "TRADING_ENABLED=false"
}
```

Position not found:

```json
{
  "detail": "position not found"
}
```

Pending order not found:

```json
{
  "detail": "pending order not found"
}
```

Bridge or MT5 failure:

```json
{
  "detail": {
    "ok": false,
    "method": "initialize",
    "message": "mt5.initialize failed",
    "last_error": null,
    "error": "..."
  }
}
```
