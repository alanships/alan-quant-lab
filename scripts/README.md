# scripts/

> 一次性脚本和测量工具。**不属于 SDK 发布范围**。
>
> One-off scripts and measurement tools. **Not part of the published SDK.**

## probe_51603.py

Empirical measurement of OKX demo's post-place query behavior.

Used to support the decision in
`.codex/tasks/001-decide-51603-retry-policy.md`.

### Run

```bash
# 1. Make sure your demo creds are exported (or sourced from .env).
export OKX_API_KEY=...
export OKX_API_SECRET=...
export OKX_PASSPHRASE=...

# 2. Run with 100 iterations (default).
poetry run python scripts/probe_51603.py

# Or scale down for a smoke test:
poetry run python scripts/probe_51603.py --n 10
```

### Output

* Console: per-iteration progress + final summary table + decision
  guidance ("Option A is safe" / "Option B is justified" / "Option C
  is needed").
* File: `scripts/probe_51603_results.json` — full per-iteration record.

### What the script does

For each iteration:

1. Generate a fresh `clOrdId` using the SDK's generator.
2. Place a far-from-market LIMIT buy on `BTC-USDT-SWAP` (won't fill).
3. **Immediately** query by `clOrdId`.
4. If first query returned `51603 Order does not exist`, retry with
   delays `[0.1, 0.25, 0.5, 1.0, 2.0]` seconds and record when (if ever)
   the order shows up.
5. Cancel the order to leave demo state clean.
6. Sleep 200 ms before next iteration.

The script uses `OkxHttpClient` directly (NOT `place_order`) so the
SDK's reconciliation logic does not mask the raw 51603 behavior we
are trying to measure.

### Decision guidance

* 0 / N raced → Option A (immediate FAILED) is safe.
* All raced cases resolved within the retry budget → Option B with
  grace ≈ `max_observed * 2`.
* Some raced cases did not resolve → Option C (configurable) and
  investigate further.

Record the chosen option in `.codex/DECISIONS.md` per the template in
`.codex/tasks/001-decide-51603-retry-policy.md`.

### Out of scope

* Real-money testing.
* Concurrent placement.
* Modifying any SDK or test code; this script is read-only WRT the
  codebase.
