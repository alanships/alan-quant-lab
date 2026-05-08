# API Reference

Status: phase-3 MVP API.

## ReliablePerpClient

```python
client = ReliablePerpClient(
    api_key="...",
    api_secret="...",
    passphrase="...",
    demo=True,
    timeout=5.0,
    reconciliation_timeout=30.0,
    reconciliation_max_attempts=3,
    base_url="https://www.okx.com",
)
```

Constructor fields:

| Field | Type | Default | Notes |
|---|---|---:|---|
| `api_key` | `str` | required | OKX API key |
| `api_secret` | `str` | required | OKX secret key |
| `passphrase` | `str` | required | OKX API key passphrase |
| `demo` | `bool` | `True` | Adds `x-simulated-trading: 1` when true |
| `timeout` | `float` | `5.0` | Per-request HTTP timeout in seconds |
| `reconciliation_timeout` | `float` | `30.0` | Total reconciliation time budget |
| `reconciliation_max_attempts` | `int` | `3` | Query attempts after ambiguous placement |
| `base_url` | `str` | `https://www.okx.com` | Override only for tests/mock server |

`close()` should be awaited when the client is no longer needed.

## place_order

```python
result = await client.place_order(
    inst_id="BTC-USDT-SWAP",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    size=Decimal("1"),
    cl_ord_id=None,
    price=None,
    pos_side="long",
    td_mode="cross",
    reduce_only=False,
)
```

The method always returns `OrderResult` for exchange business outcomes. It enters
reconciliation automatically when placement is ambiguous due to network timeout,
transport failure, selected retryable OKX codes, or 5xx responses normalized by
the HTTP layer.

Request fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `inst_id` | `str` | yes | OKX instrument ID, e.g. `BTC-USDT-SWAP` |
| `side` | `OrderSide` | yes | `BUY` or `SELL` |
| `order_type` | `OrderType` | yes | `MARKET` or `LIMIT` |
| `size` | `Decimal` | yes | OKX `sz`; must be positive |
| `cl_ord_id` | `str \| None` | no | If omitted, SDK generates an OKX-compatible ID |
| `price` | `Decimal \| None` | limit only | Required for `LIMIT` |
| `pos_side` | `str \| None` | account dependent | `long`, `short`, or `net`; demo long/short mode needed `long` |
| `td_mode` | `str` | no | `cross` or `isolated`; default `cross` |
| `reduce_only` | `bool` | no | Sent only when true |

## OrderResult

| Field | Type | Notes |
|---|---|---|
| `status` | `ResultStatus` | `CONFIRMED`, `FAILED`, or `UNKNOWN` |
| `order_status` | `OrderStatus \| None` | OKX state when known |
| `order_id` | `str \| None` | OKX `ordId` |
| `cl_ord_id` | `str` | SDK/user idempotency key |
| `inst_id` | `str` | OKX instrument ID |
| `filled_size` | `Decimal \| None` | Filled size from query result |
| `avg_price` | `Decimal \| None` | Average fill price from query result |
| `raw_response` | `dict \| None` | Original OKX response for debugging |
| `reconciliation_attempts` | `int` | Number of query attempts after ambiguous placement |
| `error` | `ReliableSdkError \| None` | Present for `FAILED`/`UNKNOWN` |
| `timestamp` | `datetime` | UTC creation timestamp |

## Status Enums

`ResultStatus`:

- `CONFIRMED`
- `FAILED`
- `UNKNOWN`

`OrderStatus`:

- `live`
- `partially_filled`
- `filled`
- `canceled`
- `mmp_canceled`

## Exceptions

The public client returns `OrderResult` for exchange business outcomes. These
exception classes are carried in `OrderResult.error` and may also be raised by
lower-level transport/configuration paths.

- `ReliableSdkError`
- `ConfigurationError`
- `AuthenticationError`
- `InsufficientFundsError`
- `InvalidOrderError`
- `OrderNotFoundError`
- `RateLimitError`
- `PositionError`
- `ExchangeMaintenanceError`
- `UnknownStateError`
- `NetworkError`
