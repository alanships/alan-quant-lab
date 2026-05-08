"""HTTP route handlers for the mock OKX server.

Mock OKX 服务器的 HTTP 路由处理器。

Endpoints implemented in v1:

v1 实现的端点：

* ``POST /api/v5/trade/order``         place order
* ``POST /api/v5/trade/cancel-order``  cancel order
* ``GET  /api/v5/trade/order``         query single order (by ordId or clOrdId)
* ``GET  /api/v5/public/time``         server time
* ``POST /_mock/faults``               (mock-only) update fault config
* ``POST /_mock/orders/{ordId}/fill``  (mock-only) inject a fill
* ``POST /_mock/reset``                (mock-only) clear all state

Endpoints under ``/_mock/`` are not part of OKX; they are control hooks
for tests.

``/_mock/`` 下的端点不属于 OKX，仅供测试控制使用。
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Any

from aiohttp import web

from tests.mock.auth import verify_request
from tests.mock.faults import FaultConfig
from tests.mock.state import MockOrder, OrderStore

# ---------------------------------------------------------------------------
# Helpers / 工具
# ---------------------------------------------------------------------------


def _ok(data: list[dict[str, Any]]) -> web.Response:
    """Build a standard OKX success envelope. / 构造 OKX 标准成功响应。"""
    return web.json_response({"code": "0", "msg": "", "data": data})


def _err(
    code: str,
    msg: str,
    data: list[dict[str, Any]] | None = None,
    *,
    http_status: int = 200,
) -> web.Response:
    """Build an OKX-shaped error response.

    构造 OKX 形态的错误响应。

    OKX returns HTTP 200 for most application-level errors and uses the
    ``code`` / ``sCode`` fields to convey the error. We mirror that.

    OKX 对绝大多数应用层错误返回 HTTP 200，靠 ``code`` / ``sCode`` 表达
    错误。我们保持一致。
    """
    return web.json_response(
        {"code": code, "msg": msg, "data": data or []},
        status=http_status,
    )


async def _run_response_delay(faults: FaultConfig) -> None:
    """Sleep ``faults.response_delay_ms`` if configured. / 按配置延迟响应。"""
    if faults.response_delay_ms > 0:
        await asyncio.sleep(faults.response_delay_ms / 1000.0)


async def _maybe_drop(faults: FaultConfig) -> None:
    """If drop_response is set, sleep effectively forever.

    若设置了 drop_response，则永久 sleep（让客户端超时）。
    """
    if faults.drop_response or faults.place_drops_response:
        await asyncio.sleep(3600)


def _consume_one_shot(faults: FaultConfig) -> None:
    """If apply_once is set and any fault is enabled, reset all faults.

    若 apply_once 开启且至少有一项故障启用，则触发后重置全部故障。
    """
    if faults.apply_once and faults.any_enabled():
        faults.reset()


async def _verify(
    request: web.Request,
    body: str,
    state: MockServerState,  # noqa: F821  (forward reference; resolved at runtime)
) -> tuple[bool, web.Response | None]:
    """Wrap auth verification, return (ok, error_response).

    封装鉴权校验，返回 (是否通过, 错误响应)。
    """
    if not state.faults.enforce_signature:
        return True, None

    headers = {k: v for k, v in request.headers.items()}
    result = verify_request(
        headers=headers,
        method=request.method,
        request_path=str(request.rel_url),
        body=body,
        expected_api_key=state.api_key,
        expected_secret=state.api_secret,
        expected_passphrase=state.passphrase,
        expected_demo=state.demo,
        timestamp_window_seconds=state.faults.enforce_timestamp_window_seconds,
    )
    if result.ok:
        return True, None
    return False, _err(result.scode, result.message)


# ---------------------------------------------------------------------------
# Mock server-wide state passed through aiohttp app
# Mock 服务器范围内的共享状态
# ---------------------------------------------------------------------------


class MockServerState:
    """Mutable shared state for the running mock. / 运行期共享状态。

    Held inside ``app["state"]`` and accessed by every handler.
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        passphrase: str,
        demo: bool,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.demo = demo
        self.store = OrderStore()
        self.faults = FaultConfig()
        # per-clOrdId 51603 race counter / 51603 竞态计数
        self._race_remaining: dict[tuple[str, str], int] = {}

    def queue_query_race(self, inst_id: str, cl_ord_id: str, n: int) -> None:
        if n > 0:
            self._race_remaining[(inst_id, cl_ord_id)] = n

    def consume_query_race(self, inst_id: str, cl_ord_id: str) -> bool:
        """Return True if this query should fake 51603 (and decrement)."""
        key = (inst_id, cl_ord_id)
        remaining = self._race_remaining.get(key, 0)
        if remaining <= 0:
            return False
        if remaining == 1:
            self._race_remaining.pop(key, None)
        else:
            self._race_remaining[key] = remaining - 1
        return True


# ---------------------------------------------------------------------------
# OKX endpoints / OKX 业务端点
# ---------------------------------------------------------------------------


async def handle_public_time(request: web.Request) -> web.Response:
    """``GET /api/v5/public/time``. / 公共时间端点。"""
    state: MockServerState = request.app["state"]
    await _run_response_delay(state.faults)
    return _ok([{"ts": str(int(time.time() * 1000))}])


async def handle_place_order(request: web.Request) -> web.Response:
    """``POST /api/v5/trade/order``. / 下单端点。"""
    state: MockServerState = request.app["state"]
    body_bytes = await request.read()
    body = body_bytes.decode("utf-8")

    ok, err = await _verify(request, body, state)
    if not ok:
        assert err is not None
        return err

    payload = await _safe_json(request, body_bytes)
    if payload is None:
        return _err("51000", "Parameter error: body must be JSON")

    inst_id = payload.get("instId", "")
    cl_ord_id = payload.get("clOrdId", "")
    side = payload.get("side", "")
    sz_str = payload.get("sz", "")
    px_str = payload.get("px", "")
    ord_type = payload.get("ordType", "")
    td_mode = payload.get("tdMode", "cross")
    pos_side = payload.get("posSide")
    reduce_only_str = str(payload.get("reduceOnly", "false")).lower()
    reduce_only = reduce_only_str in {"true", "1", "yes"}

    # Basic param validation. / 基础参数校验。
    if not all([inst_id, cl_ord_id, side, sz_str, ord_type]):
        return _ok(
            [
                {
                    "ordId": "",
                    "clOrdId": cl_ord_id,
                    "tag": "",
                    "sCode": "51000",
                    "sMsg": "Parameter error",
                }
            ]
        )

    # Apply place-time fault injection. / 应用下单层故障注入。
    faults = state.faults

    if faults.drop_response:
        _consume_one_shot(faults)
        await _maybe_drop(faults)
        return web.Response(status=503)  # unreachable

    if faults.inject_429:
        _consume_one_shot(faults)
        await _run_response_delay(faults)
        return _err(
            "50011",
            "Rate limit reached",
            [{"sCode": "50011", "sMsg": "Rate limit reached", "clOrdId": cl_ord_id}],
            http_status=429,
        )

    if faults.place_rejects_with_scode is not None:
        scode = faults.place_rejects_with_scode
        _consume_one_shot(faults)
        await _run_response_delay(faults)
        # Top-level success envelope, child sCode != "0".
        return web.json_response(
            {
                "code": "1",
                "msg": "",
                "data": [
                    {
                        "ordId": "",
                        "clOrdId": cl_ord_id,
                        "tag": "",
                        "sCode": scode,
                        "sMsg": _scode_message(scode),
                    }
                ],
            }
        )

    if faults.inject_5xx:
        _consume_one_shot(faults)
        await _run_response_delay(faults)
        return web.Response(status=503, text="upstream unavailable")

    # The two "place succeeded internally" faults must INSERT first.
    # 下面两种 "已落地但响应异常" 的故障必须先 INSERT。
    place_will_drop = faults.place_drops_response
    place_will_5xx = faults.place_succeeds_internally_but_returns_5xx

    # Insert order into the store.
    try:
        order = MockOrder(
            ord_id=OrderStore.next_ord_id(),
            cl_ord_id=cl_ord_id,
            inst_id=inst_id,
            side=side,
            sz=Decimal(sz_str),
            px=Decimal(px_str) if px_str else None,
            ord_type=ord_type,
            td_mode=td_mode,
            pos_side=pos_side,
            reduce_only=reduce_only,
        )
        state.store.add(order)
    except ValueError:
        return _ok(
            [
                {
                    "ordId": "",
                    "clOrdId": cl_ord_id,
                    "tag": "",
                    "sCode": "51200",
                    "sMsg": "Duplicate clOrdId",
                }
            ]
        )

    # MARKET orders auto-fill in this mock for simplicity.
    # MARKET 单为简化在 mock 内自动成交。
    if ord_type == "market":
        fill_px = order.px or Decimal("0")
        state.store.fill(order.ord_id, order.sz, fill_px)

    # Now serve the configured response (or fault).
    if place_will_drop:
        _consume_one_shot(faults)
        await _maybe_drop(faults)  # never returns (until shutdown)
        return web.Response(status=503)  # unreachable

    if place_will_5xx:
        _consume_one_shot(faults)
        await _run_response_delay(faults)
        return web.Response(status=503, text="upstream unavailable")

    await _run_response_delay(faults)
    return _ok(
        [
            {
                "ordId": order.ord_id,
                "clOrdId": order.cl_ord_id,
                "tag": "",
                "sCode": "0",
                "sMsg": "",
            }
        ]
    )


async def handle_cancel_order(request: web.Request) -> web.Response:
    """``POST /api/v5/trade/cancel-order``. / 撤单端点。"""
    state: MockServerState = request.app["state"]
    body_bytes = await request.read()
    body = body_bytes.decode("utf-8")

    ok, err = await _verify(request, body, state)
    if not ok:
        assert err is not None
        return err

    payload = await _safe_json(request, body_bytes)
    if payload is None:
        return _err("51000", "Parameter error: body must be JSON")

    inst_id = payload.get("instId", "")
    ord_id = payload.get("ordId")
    cl_ord_id = payload.get("clOrdId")

    order = None
    if ord_id:
        order = state.store.get_by_ord_id(ord_id)
    elif cl_ord_id:
        order = state.store.get_by_cl_ord_id(inst_id, cl_ord_id)

    if order is None:
        return _ok(
            [
                {
                    "ordId": ord_id or "",
                    "clOrdId": cl_ord_id or "",
                    "sCode": "51400",
                    "sMsg": "Cancellation failed: order does not exist",
                }
            ]
        )

    state.store.cancel(order.ord_id)
    await _run_response_delay(state.faults)
    return _ok(
        [
            {
                "ordId": order.ord_id,
                "clOrdId": order.cl_ord_id,
                "sCode": "0",
                "sMsg": "",
            }
        ]
    )


async def handle_query_order(request: web.Request) -> web.Response:
    """``GET /api/v5/trade/order``. / 查单端点。"""
    state: MockServerState = request.app["state"]
    ok, err = await _verify(request, "", state)
    if not ok:
        assert err is not None
        return err

    inst_id = request.query.get("instId", "")
    ord_id = request.query.get("ordId")
    cl_ord_id = request.query.get("clOrdId")

    if not inst_id or (not ord_id and not cl_ord_id):
        return _err("51000", "Parameter error: instId + (ordId|clOrdId) required")

    # Race-window injection happens BEFORE looking up the order.
    # 竞态窗口模拟：在查找订单之前生效。
    faults = state.faults
    if (
        cl_ord_id
        and faults.query_returns_51603_for_first_n > 0
        and not state._race_remaining
    ):
        # First-time activation: prime the per-id counter.
        state.queue_query_race(
            inst_id, cl_ord_id, faults.query_returns_51603_for_first_n
        )
        # Reset the bulk knob so future clOrdIds don't keep priming.
        faults.query_returns_51603_for_first_n = 0

    if cl_ord_id and state.consume_query_race(inst_id, cl_ord_id):
        await _run_response_delay(faults)
        return _err("51603", "Order does not exist")

    order = None
    if ord_id:
        order = state.store.get_by_ord_id(ord_id)
    elif cl_ord_id:
        order = state.store.get_by_cl_ord_id(inst_id, cl_ord_id)

    if order is None:
        await _run_response_delay(faults)
        return _err("51603", "Order does not exist")

    await _run_response_delay(faults)
    return _ok([order.to_okx_payload()])


# ---------------------------------------------------------------------------
# Mock-only control endpoints / 仅 mock 用的控制端点
# ---------------------------------------------------------------------------


async def handle_set_faults(request: web.Request) -> web.Response:
    """Replace fault config via JSON body. / 通过 JSON body 设置故障开关。"""
    state: MockServerState = request.app["state"]
    payload = await request.json()
    for key, value in payload.items():
        if hasattr(state.faults, key):
            setattr(state.faults, key, value)
    return web.json_response({"ok": True})


async def handle_inject_fill(request: web.Request) -> web.Response:
    """Manually fill an order. / 手动撮合一笔订单。"""
    state: MockServerState = request.app["state"]
    ord_id = request.match_info["ord_id"]
    payload = await request.json()
    fill_sz = Decimal(str(payload.get("fillSz", "0")))
    fill_px = Decimal(str(payload.get("fillPx", "0")))
    order = state.store.fill(ord_id, fill_sz, fill_px)
    if order is None:
        return web.json_response({"ok": False, "reason": "not found"}, status=404)
    return web.json_response({"ok": True, "state": order.state})


async def handle_reset(request: web.Request) -> web.Response:
    """Wipe all state and faults. / 清空全部状态与故障开关。"""
    state: MockServerState = request.app["state"]
    state.store.reset()
    state.faults.reset()
    state._race_remaining.clear()
    return web.json_response({"ok": True})


# ---------------------------------------------------------------------------
# Misc / 杂项
# ---------------------------------------------------------------------------


async def _safe_json(_: web.Request, body: bytes) -> dict[str, Any] | None:
    import json

    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


_SCODE_MESSAGES = {
    "51008": "Insufficient balance",
    "51020": "Order amount should be greater than minimum",
    "51120": "Insufficient margin",
    "51000": "Parameter error",
    "51200": "Duplicate clOrdId",
}


def _scode_message(scode: str) -> str:
    return _SCODE_MESSAGES.get(scode, f"Mock injected sCode {scode}")
