"""Empirical measurement of OKX demo's post-place query behavior.

经验测量：在 OKX demo 上下单成功后立即按 clOrdId 查单，看 51603 命中率
与平均解析时长。

This script supports the decision in
``.codex/tasks/001-decide-51603-retry-policy.md``:

* If 0 / N iterations ever return 51603 → Option A (immediate FAILED)
  is safe; the indexing race is not observable on OKX demo.
* If some iterations return 51603 but all resolve within ~1 s → Option
  B with a 2-3 s grace window is justified.
* If some iterations stay at 51603 longer or never resolve → Option C
  (configurable) is needed and we should investigate further before
  shipping.

Usage / 用法
-----------

Run from project root with poetry::

    poetry run python scripts/probe_51603.py --n 100

Requires the following environment variables (or a local ``.env`` you
have already exported into the shell):

    OKX_API_KEY
    OKX_API_SECRET
    OKX_PASSPHRASE

The script ALWAYS uses demo trading. It places far-from-market LIMIT
orders so they rest, queries each one, and then cancels it before the
next iteration. Total demo state change at the end should be zero.

脚本始终使用 demo trading。下的是远离盘口的 LIMIT 单（不会成交），
查单后立刻撤掉，跑完之后 demo 账户应没有遗留挂单。

Out of scope / 不在范围内
-------------------------

* Real-money testing.
* WebSocket parity.
* Concurrent placement — sequential keeps timing measurable.
* Modifying any SDK or test code; this script is a measurement tool.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path

# Make the SDK importable when running ``poetry run python scripts/...``.
# 让脚本以 ``poetry run python scripts/...`` 方式运行时也能 import SDK。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from okx_perp_reliable.http import OkxHttpClient  # noqa: E402
from okx_perp_reliable.idempotency import generate_cl_ord_id  # noqa: E402

# Retry schedule for the post-place query when the first attempt
# returns 51603. Tweak via CLI if needed.
# 首次查到 51603 时的重试节奏；如需调整可走 CLI 参数。
DEFAULT_RETRY_DELAYS_S: tuple[float, ...] = (0.1, 0.25, 0.5, 1.0, 2.0)


@dataclass
class IterationResult:
    """One iteration's measurement record. / 单次迭代的测量记录。"""

    index: int
    cl_ord_id: str
    place_status: str  # "ok" / "rejected" / "exception"
    place_scode: str | None = None
    place_smsg: str | None = None
    ord_id: str | None = None
    first_query_scode: str | None = None  # "0" if found, else "51603", "51000", ...
    first_query_state: str | None = None  # "live" / "partially_filled" / ...
    first_query_latency_ms: float = 0.0
    race_observed: bool = False
    race_resolved: bool = False
    race_resolution_ms: float | None = None
    race_attempts: int = 0
    cancel_status: str | None = None  # "ok" / "skipped" / "failed"
    error: str | None = None
    timings_ms: list[float] = field(default_factory=list)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


async def _place(
    http: OkxHttpClient,
    *,
    inst_id: str,
    cl_ord_id: str,
    side: str,
    px: Decimal,
    sz: Decimal,
    pos_side: str,
) -> dict:
    """Send a single LIMIT order. / 发送一笔 LIMIT 单。"""
    return await http.request(
        "POST",
        "/api/v5/trade/order",
        json_body={
            "instId": inst_id,
            "tdMode": "cross",
            "clOrdId": cl_ord_id,
            "side": side,
            "ordType": "limit",
            "px": str(px),
            "sz": str(sz),
            "posSide": pos_side,
        },
    )


async def _query(
    http: OkxHttpClient,
    *,
    inst_id: str,
    cl_ord_id: str,
) -> dict:
    """Query a single order by clOrdId. / 按 clOrdId 查单。"""
    return await http.request(
        "GET",
        "/api/v5/trade/order",
        params={"instId": inst_id, "clOrdId": cl_ord_id},
    )


async def _cancel(
    http: OkxHttpClient,
    *,
    inst_id: str,
    cl_ord_id: str,
) -> dict:
    """Cancel an order by clOrdId. / 按 clOrdId 撤单。"""
    return await http.request(
        "POST",
        "/api/v5/trade/cancel-order",
        json_body={"instId": inst_id, "clOrdId": cl_ord_id},
    )


def _extract_scode(envelope: dict) -> tuple[str, str]:
    """Pull (sCode, sMsg) from an OKX response envelope, preferring
    the per-item ``data[0]`` over the top-level when present.

    从 OKX 响应包络中取 (sCode, sMsg)，优先 ``data[0]`` 子项。
    """
    if isinstance(envelope, dict):
        data = envelope.get("data") or []
        if data and isinstance(data[0], dict) and "sCode" in data[0]:
            return str(data[0].get("sCode")), str(data[0].get("sMsg", ""))
        # Top-level for query GET responses.
        return str(envelope.get("code", "")), str(envelope.get("msg", ""))
    return "", ""


async def run_probe(
    *,
    n: int,
    inst_id: str,
    pos_side: str,
    far_buy_px: Decimal,
    sz: Decimal,
    inter_iter_delay_s: float,
    retry_delays_s: tuple[float, ...],
    output_path: Path,
) -> list[IterationResult]:
    """Run the probe and return per-iteration records.

    跑探测并返回每次迭代的记录。
    """
    api_key = os.environ.get("OKX_API_KEY")
    api_secret = os.environ.get("OKX_API_SECRET")
    passphrase = os.environ.get("OKX_PASSPHRASE")
    if not all([api_key, api_secret, passphrase]):
        raise SystemExit(
            "OKX_API_KEY / OKX_API_SECRET / OKX_PASSPHRASE must be set in env"
        )

    http = OkxHttpClient(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        demo=True,
        timeout=10.0,
    )

    results: list[IterationResult] = []

    try:
        for i in range(n):
            cl_ord_id = generate_cl_ord_id()
            rec = IterationResult(
                index=i,
                cl_ord_id=cl_ord_id,
                place_status="exception",
            )

            # 1. place
            try:
                t0 = time.perf_counter()
                place_resp = await _place(
                    http,
                    inst_id=inst_id,
                    cl_ord_id=cl_ord_id,
                    side="buy",
                    px=far_buy_px,
                    sz=sz,
                    pos_side=pos_side,
                )
                place_dt = (time.perf_counter() - t0) * 1000
                rec.timings_ms.append(round(place_dt, 2))
                place_scode, place_smsg = _extract_scode(place_resp)
                rec.place_scode = place_scode
                rec.place_smsg = place_smsg
                if place_scode == "0":
                    rec.place_status = "ok"
                    data0 = place_resp.get("data", [{}])[0]
                    rec.ord_id = data0.get("ordId")
                else:
                    rec.place_status = "rejected"
            except Exception as exc:  # noqa: BLE001
                rec.error = f"place: {type(exc).__name__}: {exc}"
                results.append(rec)
                await asyncio.sleep(inter_iter_delay_s)
                continue

            if rec.place_status != "ok":
                # We don't query/cancel orders that were never placed.
                results.append(rec)
                print(
                    f"[{i:3d}] place rejected sCode={rec.place_scode} "
                    f"sMsg={rec.place_smsg}"
                )
                await asyncio.sleep(inter_iter_delay_s)
                continue

            # 2. immediate query
            try:
                t0 = time.perf_counter()
                q_resp = await _query(http, inst_id=inst_id, cl_ord_id=cl_ord_id)
                q_dt = (time.perf_counter() - t0) * 1000
                rec.first_query_latency_ms = round(q_dt, 2)
                rec.timings_ms.append(round(q_dt, 2))
                q_scode, _ = _extract_scode(q_resp)
                rec.first_query_scode = q_scode
                if q_scode == "0":
                    rec.first_query_state = q_resp["data"][0].get("state")
                elif q_scode == "51603":
                    rec.race_observed = True
            except Exception as exc:  # noqa: BLE001
                rec.error = f"first_query: {type(exc).__name__}: {exc}"

            # 3. retry loop if first query was 51603
            if rec.race_observed and not rec.error:
                race_t0 = time.perf_counter()
                for attempt_idx, delay in enumerate(retry_delays_s, start=1):
                    await asyncio.sleep(delay)
                    rec.race_attempts = attempt_idx
                    try:
                        q_resp = await _query(
                            http, inst_id=inst_id, cl_ord_id=cl_ord_id
                        )
                        q_scode, _ = _extract_scode(q_resp)
                        if q_scode == "0":
                            rec.race_resolved = True
                            rec.race_resolution_ms = round(
                                (time.perf_counter() - race_t0) * 1000, 2
                            )
                            rec.first_query_state = q_resp["data"][0].get("state")
                            break
                        elif q_scode != "51603":
                            # Some other error — record and stop.
                            rec.first_query_scode = q_scode
                            break
                    except Exception as exc:  # noqa: BLE001
                        rec.error = f"retry_query: {type(exc).__name__}: {exc}"
                        break

            # 4. cancel (best effort)
            try:
                cancel_resp = await _cancel(http, inst_id=inst_id, cl_ord_id=cl_ord_id)
                c_scode, _ = _extract_scode(cancel_resp)
                rec.cancel_status = "ok" if c_scode == "0" else f"failed:{c_scode}"
            except Exception as exc:  # noqa: BLE001
                rec.cancel_status = f"exception:{type(exc).__name__}"

            results.append(rec)

            # Compact progress line.
            tag = "RACE" if rec.race_observed else "OK  "
            extra = ""
            if rec.race_observed:
                extra = (
                    f" -> resolved={rec.race_resolved} "
                    f"after_ms={rec.race_resolution_ms} "
                    f"attempts={rec.race_attempts}"
                )
            print(
                f"[{i:3d}] {tag} place_ms={rec.timings_ms[0]} "
                f"q_ms={rec.first_query_latency_ms} "
                f"cancel={rec.cancel_status}{extra}"
            )

            await asyncio.sleep(inter_iter_delay_s)
    finally:
        await http.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            [asdict(r) for r in results],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return results


def summarize(results: list[IterationResult]) -> None:
    """Print a console summary and a recommended decision.

    打印汇总并给出建议决策。
    """
    n = len(results)
    placed_ok = [r for r in results if r.place_status == "ok"]
    immediate_found = [
        r for r in placed_ok if r.first_query_scode == "0" and not r.race_observed
    ]
    raced = [r for r in placed_ok if r.race_observed]
    raced_resolved = [r for r in raced if r.race_resolved]
    raced_unresolved = [r for r in raced if not r.race_resolved]

    print()
    print("=" * 60)
    print(f"Total iterations:        {n}")
    print(f"Placed successfully:     {len(placed_ok)}")
    print(f"Immediate query found:   {len(immediate_found)}")
    print(f"Race observed (51603):   {len(raced)}")
    print(f"  resolved within retries: {len(raced_resolved)}")
    print(f"  still 51603 at end:      {len(raced_unresolved)}")

    if raced_resolved:
        ms = [r.race_resolution_ms for r in raced_resolved if r.race_resolution_ms]
        print()
        print("Race resolution latency (ms) for resolved cases:")
        print(f"  min  = {min(ms):.0f}")
        print(f"  p50  = {_percentile(ms, 0.50):.0f}")
        print(f"  p90  = {_percentile(ms, 0.90):.0f}")
        print(f"  p99  = {_percentile(ms, 0.99):.0f}")
        print(f"  max  = {max(ms):.0f}")
        print(f"  mean = {statistics.mean(ms):.0f}")

    print()
    print("Decision guidance (per .codex/tasks/001-...):")
    if not raced:
        print("  → Option A (immediate FAILED) is SAFE on this run.")
        print("    The indexing race was not observed on OKX demo.")
    elif raced_unresolved:
        print("  → Option C (configurable) is needed.")
        print(f"    {len(raced_unresolved)} cases never resolved within retries.")
        print("    Investigate why before shipping any reconciliation policy.")
    else:
        ms = [r.race_resolution_ms for r in raced_resolved if r.race_resolution_ms]
        max_ms = max(ms) if ms else 0
        print("  → Option B (retry within grace window) is JUSTIFIED.")
        print(f"    All {len(raced_resolved)} race cases resolved.")
        print(
            "    Suggested grace_seconds: "
            f"max(observed) * 2 = {max_ms * 2 / 1000:.1f}s."
        )
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="OKX demo 51603 race probe")
    parser.add_argument("--n", type=int, default=100, help="iterations (default 100)")
    parser.add_argument(
        "--inst-id",
        default=os.environ.get("OKX_E2E_INST_ID", "BTC-USDT-SWAP"),
    )
    parser.add_argument(
        "--pos-side",
        default=os.environ.get("OKX_E2E_POS_SIDE", "long"),
        help="long / short / net depending on demo account position mode",
    )
    parser.add_argument(
        "--far-buy-px",
        type=Decimal,
        default=Decimal("1000"),
        help="LIMIT buy price far from market (default 1000 USDT for BTC)",
    )
    parser.add_argument(
        "--sz",
        type=Decimal,
        default=Decimal(os.environ.get("OKX_E2E_SIZE", "1")),
    )
    parser.add_argument(
        "--inter-iter-delay-s",
        type=float,
        default=0.2,
        help="sleep between iterations to stay under demo rate limit",
    )
    parser.add_argument(
        "--output",
        default=str(_PROJECT_ROOT / "scripts" / "probe_51603_results.json"),
    )
    args = parser.parse_args()

    results = asyncio.run(
        run_probe(
            n=args.n,
            inst_id=args.inst_id,
            pos_side=args.pos_side,
            far_buy_px=args.far_buy_px,
            sz=args.sz,
            inter_iter_delay_s=args.inter_iter_delay_s,
            retry_delays_s=DEFAULT_RETRY_DELAYS_S,
            output_path=Path(args.output),
        )
    )
    summarize(results)
    print(f"\nFull detail written to: {args.output}")


if __name__ == "__main__":
    main()
