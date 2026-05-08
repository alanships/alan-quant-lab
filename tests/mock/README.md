# Mock OKX server

> 进程内运行的 OKX v5 REST API mock，用于在 CI 中确定性地复现交易所端故障。
>
> In-process mock of OKX v5 REST API for deterministic reproduction of
> exchange-side faults in CI.

This is a **test fixture**, not a published part of the SDK. It lives
under `tests/mock/` so it is not bundled in the wheel.

它是 **测试夹具**，不属于发布的 SDK；放在 `tests/mock/` 下不会被打包。

---

## 为什么需要它 / Why this exists

The SDK's central promise is that `place_order` returns
`CONFIRMED | FAILED | UNKNOWN` regardless of network conditions. The
only way to verify that promise is to deliberately produce the failure
modes. OKX demo trading does not let us do that on demand. This mock
does.

SDK 的核心承诺是 `place_order` 在任何网络情况下都会返回 `CONFIRMED |
FAILED | UNKNOWN`。验证这个承诺的唯一办法就是主动制造故障。OKX demo
trading 不允许我们随时触发故障，这个 mock 可以。

The failure modes are not invented; they are observed in production
exchange code (e.g. HTX has an internal `abnormal-check` service that
exists precisely to handle "place succeeded but client never knew").
See `docs/why.zh-CN.md` for the case study.

故障模式并非凭空捏造，而是在生产级交易所代码中实际观察到的。例如 HTX
有一个 `abnormal-check` 服务，专门处理"下单已落地但客户端未知"。详见
`docs/why.zh-CN.md`。

---

## 端点 / Endpoints

### OKX endpoints (mirrors the real API)

| Method | Path                            | Behavior |
|--------|---------------------------------|----------|
| GET    | `/api/v5/public/time`           | Returns server time. No auth. |
| POST   | `/api/v5/trade/order`           | Place order. Validates signature. |
| POST   | `/api/v5/trade/cancel-order`    | Cancel order by `ordId` or `clOrdId`. |
| GET    | `/api/v5/trade/order`           | Query single order by `ordId` or `clOrdId`. |

### Mock-only control endpoints

| Method | Path                                 | Body                              |
|--------|--------------------------------------|-----------------------------------|
| POST   | `/_mock/faults`                      | `{"<switch>": true|false|number}` |
| POST   | `/_mock/orders/{ordId}/fill`         | `{"fillSz": "...", "fillPx": "..."}` |
| POST   | `/_mock/reset`                       | (empty)                           |

You can also flip switches in-process via `mock.faults.<switch> = ...`.

也可以在进程内直接 `mock.faults.<switch> = ...`。

---

## 故障开关 / Fault switches

| Switch | What it does | Models the real-world scenario |
|--------|--------------|--------------------------------|
| `response_delay_ms` | Add fixed delay before each response | High exchange latency |
| `drop_response` | Read request, sleep forever | Response lost in transit / TCP black hole |
| `inject_5xx` | Return HTTP 503 *without* mutating state | OKX gateway error, order not accepted |
| `inject_429` | Return HTTP 429 + sCode 50011 | Rate-limited |
| **`place_succeeds_internally_but_returns_5xx`** | INSERT order, then return 503 | **Killer fault**: client cannot tell if order placed |
| `place_drops_response` | INSERT order, then sleep forever | Same as above but as a timeout |
| `query_returns_51603_for_first_n` | First N queries-by-clOrdId fake "not found" even though order exists | Indexing race window between place and query |
| `place_rejects_with_scode` | Return success envelope with non-"0" sCode | Application-layer rejections (insufficient balance, etc.) |
| `enforce_signature` | When False, skip auth | Pure transport tests |
| `enforce_timestamp_window_seconds` | OKX-style 30s window | Clock-drift behavior |
| `apply_once` | Reset after first triggered fault | "First request fails, retry succeeds" |

The two `place_*_returns/drops` switches are the most important. They
are the only way to write a test that proves
`reconciliation -> CONFIRMED` works.

那两个 `place_*_returns/drops` 开关是最重要的——它们是唯一能写出
"reconciliation -> CONFIRMED" 测试的途径。

---

## 用法 / Usage

### As an `async with` context manager

```python
from tests.mock import run_mock_okx

async def test_reconciliation_finds_order_after_5xx():
    async with run_mock_okx() as mock:
        mock.faults.place_succeeds_internally_but_returns_5xx = True

        client = ReliablePerpClient(
            api_key=mock.api_key,
            api_secret=mock.api_secret,
            passphrase=mock.passphrase,
            demo=mock.demo,
            base_url=mock.base_url,
        )
        result = await client.place_order(
            inst_id="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("1"),
            price=Decimal("10000"),
        )
        assert result.status is ResultStatus.CONFIRMED
        assert result.reconciliation_attempts >= 1
```

### Direct HTTP for exotic tests

```python
async with aiohttp.ClientSession() as session:
    await session.post(
        f"{mock.base_url}/_mock/faults",
        json={"inject_429": True, "apply_once": True},
    )
```

---

## 设计取舍 / Design choices

* **In-process, port 0.** No fixed port collision in CI; `mock.base_url`
  exposes the OS-assigned port. 进程内启动 + 操作系统分配端口，避免 CI
  端口冲突。
* **Independent signing implementation.** The mock verifies signatures
  itself instead of importing from `okx_perp_reliable._internal.signing`,
  so a bug in the SDK's signing module shows up as a self-test failure.
  独立实现签名校验，SDK 签名 bug 会立刻在自测中暴露。
* **No threading.** Everything runs on the test event loop; the store
  is plain dicts. 不引入线程，store 用普通 dict。
* **Tiny fault surface (~10 switches).** Combinations cover most
  scenarios; resist adding more without evidence. 故障开关刻意精简，
  组合即可覆盖大多数场景，加新开关需有真实证据。
* **OKX response shape is preserved.** Field names and envelope match
  the real API so SDK code paths don't diverge. 响应字段与真实 OKX 对齐。

---

## 已知限制 / Known limitations

* No batch order endpoint (`/trade/batch-orders`). v1 SDK doesn't use it.
* No WebSocket. v1 SDK is REST-only.
* No realistic fee/funding accounting. Only enough fields to satisfy
  the SDK's parsing.
* MARKET orders auto-fill at the price you pass in (`px`). Don't read
  too much into the prices.

---

## 何时该改它 / When to extend

* SDK adds a new endpoint → add a route handler that mirrors OKX.
* You discover a new failure mode in production → add ONE switch with
  a verbose name and a self-test, update this README's table.
* Never extend "because Codex suggested it"; extend because a real
  scenario in `docs/why.md` requires it.
