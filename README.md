# okx-perp-reliable

[![CI](https://github.com/alanships/alan-quant-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/alanships/alan-quant-lab/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/okx-perp-reliable.svg)](https://pypi.org/project/okx-perp-reliable/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Reliable asyncio SDK for OKX USDT-margined perpetual swap REST order placement.

![Status Beta](https://img.shields.io/badge/status-beta-yellow)

## Why This Exists

`place_order()` can become ambiguous when OKX accepts an order but the client
times out before receiving the response. This SDK uses idempotent `clOrdId`
values and bounded query-by-`clOrdId` reconciliation so callers receive one of
three explicit outcomes: `CONFIRMED`, `FAILED`, or `UNKNOWN`. See
[docs/why.md](docs/why.md) for the full rationale.

## Install

```bash
pip install okx-perp-reliable
```

## Minimal Example

```python
from decimal import Decimal
from okx_perp_reliable import OrderSide, OrderType, ReliablePerpClient
async def main() -> None:
    client = ReliablePerpClient(api_key="...", api_secret="...", passphrase="...", demo=True)
    result = await client.place_order(inst_id="BTC-USDT-SWAP", side=OrderSide.BUY, order_type=OrderType.MARKET, size=Decimal("0.01"), pos_side="long")
```

## Mock Infrastructure

The deterministic in-process OKX mock used by integration tests is documented
in [tests/mock/README.md](tests/mock/README.md). It is test infrastructure, not
part of the published SDK package.

## License And Author

MIT License. Maintained by Alan.

中文说明见 [README.zh-CN.md](README.zh-CN.md).
