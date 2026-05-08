# Timeout Behavior Notes

Status: demo auth, order placement, and query-by-clOrdId verified.

## What is known from OKX docs

- OKX documents endpoint request timeout error `50004` as not proving success or
  failure. The caller must check the request result.
- This matches the SDK's core design: timeout after `POST /api/v5/trade/order`
  must trigger reconciliation via `GET /api/v5/trade/order?instId=...&clOrdId=...`.

## Live demo checks completed

Date: 2026-05-04.

- Private demo authentication passed via `GET /api/v5/account/balance` with
  `code=0`.
- Demo market order passed on `BTC-USDT-SWAP` with `tdMode=cross` and
  `posSide=long`.
- Query-by-`clOrdId` passed via `GET /api/v5/trade/order`; OKX returned
  `state=filled`, filled size, and average price.
- Local networking note: `aiohttp` needed `trust_env=True` in this environment
  to use the same proxy path as `curl`.

## Remaining manual timeout test plan

1. Simulate client-side timeout before response read:
   - set very small HTTP timeout, or
   - block network after request is sent.
2. Query by `clOrdId`.
3. Record whether OKX returns:
   - confirmed order state,
   - `51603` order not found,
   - transient network/server errors.

## Expected SDK behavior

- Confirmed query result -> `OrderResult(status=CONFIRMED)`.
- `51603` -> `OrderResult(status=FAILED, error=OrderNotFoundError)`.
- Repeated timeout/network errors until max attempts -> `OrderResult(status=UNKNOWN)`.
