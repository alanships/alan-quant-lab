# Mock OKX server — design

> 设计文档：为什么本项目需要一个进程内 OKX REST mock，它如何与 v1 的核心承诺挂钩，以及如何被 reconciliation 单测复用。
>
> Why this project needs an in-process OKX REST mock, how it ties into
> v1's core promise, and how it is reused by reconciliation unit tests.

---

## 一、动机 / Motivation

The SDK's central promise (per `.codex/PROJECT_CONSTITUTION.md` §一) is
that `place_order` returns one of three deterministic outcomes:

SDK 的核心承诺是 `place_order` 在任何条件下都返回三种确定状态之一：

* `CONFIRMED` — exchange acknowledged the order
* `FAILED` — exchange did not accept it
* `UNKNOWN` — reconciliation could not decide

The promise is only as strong as our ability to **reproduce the
failure modes** under test. OKX demo trading returns "happy path"
responses; it does not let us produce, on demand, "place succeeded but
the response was lost" or "query returns 51603 within the indexing
race window".

只有当我们能在测试中**复现故障模式**，这个承诺才有效。OKX demo
trading 默认返回正常响应，不能按需生成"下单已落地但响应丢失"或
"查单在索引竞态窗口内返回 51603"等故障。

These failure modes are not invented. They are observed in real
exchange code:

这些故障并非凭空捏造，而是在真实交易所代码中观察到的：

* **HTX `abnormal-check`**: an internal service that scans every 10
  seconds for orders stuck in `new` for more than 5 minutes. Its
  existence is the simplest proof that "place succeeded internally but
  client never saw it" happens at production scale.
* **HTX `TimeWeightedTriggerServiceImpl`**: contains an explicit
  comment that strategy stop orders depend on a Kafka binlog consumer's
  speed; a slow consumer can show stale state to the user.
* **HTX `OrderValidationServiceImpl#allowSeflMatchMaker`**: an Apollo-
  config kill-switch the operations team can flip during incidents —
  evidence that "exchange-side guarantees" can be reduced live.

These map directly to specific switches in `tests/mock/faults.py`.

---

## 二、设计原则 / Design principles

1. **Mock is a test fixture, not a published artifact.** It lives
   under `tests/mock/`; the wheel does not include it.

   Mock 是测试夹具，不进入发布包。

2. **The mock implements signature verification independently.** Any
   bug in the SDK's signing module shows up as a self-test failure of
   the round-trip with `tests/mock/auth.py`. We do *not* import
   `okx_perp_reliable._internal.signing` from the mock.

   Mock 独立实现签名校验。SDK 签名模块若有 bug，会作为 mock 与 SDK
   之间的 round-trip 失败暴露出来。

3. **Tiny fault surface (~10 switches).** Combinations cover most
   scenarios. Resist adding switch #11 unless a real
   `docs/why.md`-grade scenario requires it.

   故障开关刻意精简（约 10 个），加新开关须有真实场景证据。

4. **Verbose switch names.** A test reading `mock.faults.
   place_succeeds_internally_but_returns_5xx = True` is
   self-documenting.

   开关命名故意冗长，使测试代码即文档。

5. **Single event loop, no threads.** The mock runs on the test event
   loop. State is plain dicts.

   单事件循环、无线程。状态用普通 dict。

6. **OS-assigned port (port 0).** No CI port collisions.

   端口由操作系统分配（port 0），避免 CI 端口冲突。

---

## 三、故障矩阵 / Fault matrix

The fault matrix below is the authoritative surface. Each switch maps
to (a) a real-world scenario, (b) the SDK code path it must exercise,
and (c) the assertion the corresponding reconciliation test should
make.

下表是故障矩阵的权威清单。每个开关对应：(a) 真实世界场景，(b) 应触发
的 SDK 代码路径，(c) reconciliation 测试应做的断言。

| Switch | Real-world cause | SDK code path | Test assertion |
|---|---|---|---|
| `inject_5xx` | OKX gateway 503, order not accepted | place gets HTTP 5xx → reconcile → query returns 51603 | `result.status == FAILED` |
| `place_succeeds_internally_but_returns_5xx` | Exchange accepted order; response lost in transit | place gets HTTP 5xx → reconcile → query finds order | `result.status == CONFIRMED`, `reconciliation_attempts >= 1` |
| `place_drops_response` | TCP black hole; same as above but as timeout | place times out → reconcile → query finds order | `result.status == CONFIRMED` |
| `query_returns_51603_for_first_n` | Indexing race window between place and query | reconcile sees 51603 transiently before order shows up | `result.status == CONFIRMED` after retries |
| `inject_429` | Rate limit hit | place gets HTTP 429 → exception path | `RateLimitError` raised |
| `place_rejects_with_scode="51008"` | Insufficient balance | place returns success envelope with non-"0" sCode | `InsufficientFundsError` raised |
| `place_rejects_with_scode="51120"` | Insufficient margin | same as above | `InsufficientFundsError` raised |
| `place_rejects_with_scode="51000"` | Parameter error | same as above | `InvalidOrderError` raised |
| `enforce_timestamp_window_seconds`<0.1 with stale ts | Clock drift | place returns sCode 50112 | `AuthenticationError` raised |
| `drop_response` (without `place_drops_response`) | Pure transport timeout, no order side-effect | place times out → reconcile → 51603 | `result.status == FAILED` |
| `apply_once` | "First request fails, retry succeeds" | first place hits fault, second succeeds | exercise retry-after-timeout if/when implemented |

---

## 四、与 reconciliation 单测的衔接 / Integration with reconciliation tests

The existing `tests/unit/test_reconciliation.py` uses an in-test
`FakeHttp` to inject canned responses. That tests the
**OrderReconciler logic in isolation**: given a sequence of HTTP
responses, what does the reconciler do?

既有的 `tests/unit/test_reconciliation.py` 用进程内 `FakeHttp` 注入伪
响应，测的是 reconciler 在给定响应序列下的行为，是单元层面的隔离测试。

The mock complements that with **end-to-end tests**: real signed
HTTP, real aiohttp transport, real failure modes. A reconciliation
fix that passes unit tests but does not actually result in
`CONFIRMED` against a real-shaped server will fail here.

Mock 在此基础上补全端到端测试：真实签名 HTTP、真实 aiohttp 传输、真实
故障形态。reconciliation 的修复若仅通过单测但在真实形态下没拿到
`CONFIRMED`，会在这里失败。

The split is:

| Layer | Where | What it proves |
|---|---|---|
| Pure logic | `tests/unit/test_reconciliation.py` + `FakeHttp` | Reconciler decisions on response sequences |
| Wire format | `tests/mock/test_mock_server.py` | Mock produces OKX-shaped responses; signing round-trips |
| End-to-end | (future) `tests/integration/test_reconciliation_with_mock.py` | SDK + mock together yield the documented `CONFIRMED|FAILED|UNKNOWN` outcomes |

---

## 五、运行方式 / How to run

```bash
poetry install
poetry run pytest tests/mock/ -v
# or run only the mock self-tests
poetry run pytest tests/mock/test_mock_server.py -v
```

There is no demo trading account requirement. The mock has no external
dependency. Tests should run in well under 10 seconds on a laptop.

无需 demo trading 账号，无外部依赖；普通笔记本应在 10 秒内跑完。

---

## 六、不在范围内的 / Not in scope

* **Batch order endpoint (`/trade/batch-orders`).** v1 SDK uses single
  order placement only.
* **WebSocket.** v1 is REST-only.
* **Realistic fee / funding accounting.** Only enough fields to pass
  the SDK's parser.
* **Multi-instrument matching engine.** MARKET orders auto-fill at the
  passed-in price. Don't read meaning into the prices.
* **Real OKX rate-limit modelling.** `inject_429` is binary, not
  quota-based.

These are deliberate omissions and should remain so until a real
scenario in `docs/why.md` justifies expansion.

以上是刻意省略，只有 `docs/why.md` 中出现真实场景才考虑扩展。

---

## 七、与 HTX 代码证据的对应 / Provenance from HTX code

For the public-facing case study (see `docs/why.zh-CN.md`), the
following HTX repository observations support the corresponding mock
features:

公开案例（见 `docs/why.zh-CN.md`）中，以下 HTX 仓库观察支撑对应的 mock
特性：

| HTX evidence | Maps to switch |
|---|---|
| `abnormal-check/README.md`: 5-minute scan for stuck `new` orders | `place_succeeds_internally_but_returns_5xx`, `place_drops_response` |
| `linear-swap-trade-service/.../OrderValidationServiceImpl.java#allowSeflMatchMaker` Apollo kill-switch | (out of scope for v1; documents v2 client-side guard) |
| `linear-swap-trade-service/.../TimeWeightedTriggerServiceImpl.java` BinlogConsumer comment | (out of scope for v1; documents v2 local trigger engine) |
| `linear-swap-common-entity/.../ErrorCode.java` 1692-line file | shape of `place_rejects_with_scode` mapping |

These references are intentionally repository-relative paths so the
case study remains verifiable.

引用刻意使用仓库相对路径，便于公开案例可被复核。
