# Design

## Goal

`okx-perp-reliable` wraps OKX USDT-margined perpetual swap REST order placement
with deterministic final order results under timeout and network ambiguity.

The public contract is deliberately small: `ReliablePerpClient.place_order()`
returns `CONFIRMED`, `FAILED`, or `UNKNOWN`.

## Non-goals

- No exchanges except OKX.
- No WebSocket.
- No spot, coin-margined swaps, options, portfolio/position management, or
  backtesting.
- No official OKX Python SDK dependency.

## Components

- `client.py`: public `ReliablePerpClient` orchestration.
- `http.py`: `aiohttp` transport, signing headers, demo header, timeout and
  HTTP error normalization.
- `_internal/signing.py`: HMAC-SHA256 + Base64 signing.
- `idempotency.py`: generated `clOrdId` and replaceable local `StateStore`.
- `reconciliation.py`: query-by-`clOrdId` flow after ambiguous placement.
- `_internal/error_mapping.py`: OKX `sCode` to SDK exception mapping.
- `models.py` / `enums.py` / `exceptions.py`: public data contract.

## Order flow

1. Validate `OrderRequest`.
2. Generate `clOrdId` if not supplied.
3. Record local pending state.
4. Send `POST /api/v5/trade/order`.
5. If `sCode == "0"`, return `CONFIRMED`.
6. If OKX returns deterministic business failure, map error and return `FAILED`.
7. If timeout, connection error, `50004`, or ambiguous 5xx occurs, reconcile.
8. Query `GET /api/v5/trade/order?instId=...&clOrdId=...`.
9. Return:
   - `CONFIRMED` if order is found,
   - `FAILED` if OKX returns `51603`,
   - `UNKNOWN` after max attempts/deadline.

## State model

The first implementation uses `InMemoryStateStore`, but the protocol is stable:

- `record_pending(cl_ord_id, request)`
- `update_status(cl_ord_id, result)`
- `get(cl_ord_id)`
- `list_pending(older_than)`

This keeps v1 simple while leaving room for Redis/SQLite later without changing
the public client API.

## Reliability boundaries

The SDK can remove client-side uncertainty for most timeout paths, but it cannot
guarantee final truth when both placement response and all reconciliation queries
fail. That state must be explicit as `UNKNOWN`, never hidden as success or failure.

## Security

- Never log `api_secret` or `passphrase`.
- Do not store credentials in examples.
- Keep demo/prod mode explicit; demo mode injects `x-simulated-trading: 1`.

