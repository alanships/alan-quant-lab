# OKX API Notes

Sources:

- OKX v5 API guide: https://www.okx.com/docs-v5/en/
- REST authentication section: https://www.okx.com/docs-v5/en/#overview-rest-authentication
- Place order endpoint: https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-place-order
- Order details endpoint: https://www.okx.com/docs-v5/en/#order-book-trading-trade-get-order-details
- REST error codes: https://www.okx.com/docs-v5/en/#error-code-rest-api
- OKX API FAQ: https://www.okx.com/help/api-faq

Fetched/reviewed on: 2026-05-04.

## Authentication

- Private REST requests require `OK-ACCESS-KEY`, `OK-ACCESS-SIGN`,
  `OK-ACCESS-TIMESTAMP`, `OK-ACCESS-PASSPHRASE`, and JSON content type.
- Signature pre-hash string is `timestamp + method + requestPath + body`.
- `method` must be uppercase.
- GET query string belongs in `requestPath`; GET body is empty.
- POST body must be the exact JSON string sent on the wire.
- Timestamp is ISO-8601 UTC with milliseconds, e.g. `2020-12-08T09:08:57.715Z`.
- OKX notes that a request expires 30 seconds after the timestamp, so phase 2
  should either trust local NTP or expose a clock-drift diagnostic.

## Demo trading

- Demo trading uses the normal REST base URL plus request header
  `x-simulated-trading: 1`.
- OKX FAQ says demo API keys must be created from the demo trading area:
  `Trading > Demo Trading > Personal Center > Create Demo Account API key`.
- Account credentials are still TODO.

## Place order

- Endpoint: `POST /api/v5/trade/order`.
- v1 request fields map:
  - `inst_id` -> `instId`, e.g. `BTC-USDT-SWAP`
  - `td_mode` -> `tdMode`, `cross` or `isolated`
  - `side` -> `side`, `buy` or `sell`
  - `order_type` -> `ordType`, `market` or `limit`
  - `size` -> `sz`
  - `price` -> `px`, required by SDK for limit orders
  - `cl_ord_id` -> `clOrdId`
  - `pos_side` -> `posSide`, only when user needs long/short mode
  - `reduce_only` -> `reduceOnly`
- OKX response uses top-level `code` and per-order `sCode`; `sCode == "0"`
  means the order request succeeded.

## clOrdId notes

- `clOrdId` is user-defined and can be used to query, cancel, and amend orders.
- It must be unique among current pending orders.
- Once an order reaches a terminal state, OKX may allow reuse; the SDK should
  still generate globally unique IDs by default to avoid ambiguous reconciliation.
- If multiple historical orders share a `clOrdId`, OKX may return only the
  latest match. This is why the SDK should never intentionally reuse generated
  IDs.
- Planned generated format: `sdk` + 26 alphanumeric characters, max 29 chars,
  starting with a letter and below OKX's 32-char limit.

## Query order

- Endpoint: `GET /api/v5/trade/order?instId=...&clOrdId=...`.
- Either `ordId` or `clOrdId` is required. If both are passed, `ordId` wins.
- Reconciliation should query by `clOrdId` because an order timeout may happen
  before the SDK receives `ordId`.
- OKX error `51603` means order does not exist and maps to `OrderNotFoundError`
  for reconciliation.

## Dependency red line

- Do not depend on OKX's official `python-okx` package or any other exchange SDK.
- Phase 2 must implement signing, headers, timeout handling, and demo header
  injection directly on top of `aiohttp`.
- Keep dependencies to the project plan: `aiohttp`, `pydantic v2`,
  `pytest`, `pytest-asyncio`, `poetry`, `ruff`, `black`.

