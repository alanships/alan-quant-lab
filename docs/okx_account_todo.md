# OKX Account TODO

Owner: Alan.

Status: initial demo credentials received and verified locally.

1. Rotate the exposed demo API key after local validation is complete.
2. Store the new values only in local environment variables:
   - `OKX_API_KEY`
   - `OKX_API_SECRET`
   - `OKX_PASSPHRASE`
3. Confirm the new demo key can access `BTC-USDT-SWAP`.

Integration tests use environment variables and do not commit secrets.
