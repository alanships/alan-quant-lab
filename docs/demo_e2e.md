# Demo E2E

This document describes the verified OKX demo trading flow.

## Setup

Create a demo trading API key in OKX, then keep credentials local:

```bash
cp .env.example .env
# edit .env
chmod 600 .env
set -a; source .env; set +a
```

Required variables:

```bash
OKX_API_KEY=...
OKX_API_SECRET=...
OKX_PASSPHRASE=...
```

Optional variables:

```bash
OKX_E2E_INST_ID=BTC-USDT-SWAP
OKX_E2E_POS_SIDE=long
OKX_E2E_SIZE=1
```

## Run

```bash
PYTHONPATH=src /opt/anaconda3/bin/python3 -m pytest -q tests/integration/test_demo_e2e.py
```

The integration test does two things:

1. Calls `GET /api/v5/account/balance` to verify private demo authentication.
2. Places a demo market order, then queries it by `clOrdId`.

This uses demo trading, but it still changes the demo account state.

## Verified Behavior

Observed on 2026-05-04:

- Private balance endpoint returned `code=0`.
- `BTC-USDT-SWAP` market buy with `tdMode=cross`, `posSide=long`, and size `1`
  returned `CONFIRMED`.
- Query by `clOrdId` returned `state=filled`, filled size, and average price.

## Troubleshooting

- If `aiohttp` times out while `curl` works, keep `trust_env=True` so Python
  uses proxy environment variables.
- If OKX returns `Parameter posSide error`, your account is likely in long/short
  mode. Set `OKX_E2E_POS_SIDE=long` or `short` as appropriate.
- If credentials were pasted into chat or logs, rotate the demo key after
  validation.

