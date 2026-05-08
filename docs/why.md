# Why this SDK exists

## 1. The opening scene

It is 2 a.m. Your strategy sends a limit order for an OKX perpetual swap. The
code calls `place_order()`, waits 30 seconds, and receives only an `aiohttp`
timeout. The hard question is not "did the code raise?" It is: did the order
reach OKX?

You open the trading UI and do not see the order yet. You inspect the logs and
find only a timeout exception, with no OKX order ID. If you retry blindly, you
may place a duplicate order in the same direction. If you assume failure, you
may ignore an order that was accepted but is not visible yet. If the strategy
stops for manual review, your exposure keeps moving.

This is the problem this SDK handles. It does not predict the market or manage
risk for you. It turns "the order result is unclear" from a loose log line into
a program contract.

## 2. Why this happens technically

A REST order placement is not an atomic event. After the client sends an HTTP
request, the request may pass through the gateway and even be processed by
backend systems, while the response is interrupted on its way back. To
`aiohttp`, this is just a `TimeoutError`. To the trading system, the order may
already exist.

HTTP 5xx does not prove the order failed either. Large matching systems usually
have gateways, risk checks, matching, and order indexes. When a gateway returns
5xx, the client only knows that this HTTP call did not produce a usable
response. The status code alone cannot prove that the order was never accepted.

OKX's `clOrdId` mechanism is the key clue for handling this problem. The OKX v5
documentation exposes the client-supplied order ID `clOrdId` on the place-order
endpoint and supports querying an order by `clOrdId`; it also notes that if one
`clOrdId` is associated with multiple orders, the query returns only the latest
one. The practical rule is therefore to generate a unique `clOrdId` every time
and use it for reconciliation. See the OKX v5 API documentation:
<https://www.okx.com/docs-v5/en/>.

There is also a general distributed-systems issue. Any system that places an
order first and updates a query index later can have a short window where the
order is real but a lookup by ID returns "not found". This is not special to
one venue. It is a common indexing race window in large-scale place + query
systems.

## 3. The contract this SDK provides

This SDK narrows `place_order()` to three states.

`CONFIRMED` means OKX has acknowledged the order. The result includes
`order_status`, which tells whether the order is resting, partially filled, or
filled.

`FAILED` means the SDK has enough information to conclude that the order will
not exist on OKX. You can submit again with a fresh `clOrdId` instead of
reusing the old one.

`UNKNOWN` means the SDK still cannot decide within bounded attempts and time.
Do not retry automatically. Inspect the account, orders, and logs manually.
`UNKNOWN` does not hide an error; it admits the system boundary.

Two mechanisms deliver this contract. First, every call gets a unique
SDK-generated or user-supplied `clOrdId`, and the SDK records local pending
state before the HTTP request leaves the process. This is a lightweight
write-ahead step. Second, whenever placement is ambiguous, such as a timeout,
5xx, or dropped response, the SDK queries by `clOrdId` with bounded retries.

During reconciliation, OKX sCode `51603` (order does not exist) becomes a
definitive `FAILED` by default. If you have measured a short indexing race
window in your own environment, you can explicitly set
`reconciliation_51603_grace_seconds` so the SDK keeps checking inside that
window. This setting is opt-in. There is no recommended fixed value; it should
come from your account mode, network, and measured latency.

## 4. What this SDK does not do

This is not a multi-venue wrapper. It only targets OKX USDT-margined perpetual
swaps. It is not a position manager, fund manager, or risk system. It is not a
strategy framework and not a backtester.

It also does not use WebSocket. The first version covers REST order placement
and query-by-`clOrdId` reconciliation only. Real-time fills, order streams, and
account pushes are outside the current contract.

It cannot prevent stop-loss triggers from being delayed by venue internals. It
cannot prevent forced liquidation. It cannot prevent auto-deleveraging. Those
are platform behaviors, not SDK return-value guarantees.

It cannot fix downtime either. If OKX is under long maintenance or unavailable,
the SDK can only return `UNKNOWN` after bounded retries or raise transport
errors. That is not a design failure. It is the correct signal that the caller
does not have enough information to keep acting automatically.

This restraint matters. A reliable SDK should not pretend that it has handled
every trading problem. It should give clear answers only inside the boundary it
can actually own.

## 5. How to start

The example below uses `demo=True`, so it does not touch the live trading
environment. Put demo credentials in environment variables before running it.

```python
# pip install okx-perp-reliable
import asyncio
import os
from decimal import Decimal

from okx_perp_reliable import (
    OrderSide,
    OrderType,
    ReliablePerpClient,
    ResultStatus,
)


async def main() -> None:
    client = ReliablePerpClient(
        api_key=os.environ["OKX_API_KEY"],
        api_secret=os.environ["OKX_API_SECRET"],
        passphrase=os.environ["OKX_PASSPHRASE"],
        demo=True,
    )
    try:
        result = await client.place_order(
            inst_id="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("1"),
            price=Decimal("10000"),
            pos_side="long",
        )
    finally:
        await client.close()

    match result.status:
        case ResultStatus.CONFIRMED:
            print("confirmed", result.order_status)
        case ResultStatus.FAILED:
            print("failed", result.error)
        case ResultStatus.UNKNOWN:
            print("unknown; inspect manually")


if __name__ == "__main__":
    asyncio.run(main())
```
