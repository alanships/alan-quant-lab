"""Self-tests for the mock OKX server.

Mock OKX 服务器的自测。

These tests prove that:

这些测试证明：

1. The mock signs/verifies requests the same way the real OKX does (so
   the SDK's signing module can be tested against it).
2. Each fault-injection switch produces the response shape that triggers
   the corresponding SDK code path.
3. Reset / one-shot semantics work as documented.

1. mock 与真实 OKX 使用一致的签名校验，可用于验证 SDK 的签名模块。
2. 每个故障开关都会产生对应的响应形态，驱动 SDK 正确分支。
3. reset 与 one-shot 语义如文档所述。

Style note: this project's existing tests drive coroutines via
``asyncio.run`` rather than the ``@pytest.mark.asyncio`` marker. We
keep the same convention here so the mock package needs no extra
pytest-asyncio configuration.

风格说明：本项目既有测试通过 ``asyncio.run`` 调用协程，而非
``@pytest.mark.asyncio`` 标记。这里沿用同一规范，无需额外配置
pytest-asyncio。
"""

from __future__ import annotations

import asyncio
import json
from asyncio import run

import aiohttp
import pytest

from okx_perp_reliable._internal.signing import generate_timestamp, sign_request
from tests.mock.server import MockOkxServer, run_mock_okx

# ---------------------------------------------------------------------------
# Helpers / 工具
# ---------------------------------------------------------------------------


def _signed_headers(
    *,
    method: str,
    request_path: str,
    body: str,
    api_key: str,
    api_secret: str,
    passphrase: str,
    demo: bool,
) -> dict[str, str]:
    timestamp = generate_timestamp()
    headers = {
        "Content-Type": "application/json",
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": sign_request(
            timestamp=timestamp,
            method=method,
            request_path=request_path,
            body=body,
            secret=api_secret,
        ),
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": passphrase,
    }
    if demo:
        headers["x-simulated-trading"] = "1"
    return headers


def _build_place_body(cl_ord_id: str) -> str:
    return json.dumps(
        {
            "instId": "BTC-USDT-SWAP",
            "tdMode": "cross",
            "clOrdId": cl_ord_id,
            "side": "buy",
            "ordType": "limit",
            "px": "10000",
            "sz": "1",
        }
    )


def _signed_headers_for_place(mock: MockOkxServer, body: str) -> dict[str, str]:
    return _signed_headers(
        method="POST",
        request_path="/api/v5/trade/order",
        body=body,
        api_key=mock.api_key,
        api_secret=mock.api_secret,
        passphrase=mock.passphrase,
        demo=mock.demo,
    )


# ---------------------------------------------------------------------------
# Tests / 测试
# ---------------------------------------------------------------------------


def test_public_time_does_not_require_signature() -> None:
    run(_public_time_does_not_require_signature())


async def _public_time_does_not_require_signature() -> None:
    async with run_mock_okx() as mock:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{mock.base_url}/api/v5/public/time") as resp:
                assert resp.status == 200
                payload = await resp.json()
        assert payload["code"] == "0"
        assert "ts" in payload["data"][0]


def test_signed_place_order_succeeds() -> None:
    run(_signed_place_order_succeeds())


async def _signed_place_order_succeeds() -> None:
    async with run_mock_okx() as mock:
        body = _build_place_body("sdkTEST0001")
        headers = _signed_headers_for_place(mock, body)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{mock.base_url}/api/v5/trade/order",
                data=body,
                headers=headers,
            ) as resp:
                payload = await resp.json()
        assert payload["code"] == "0"
        assert payload["data"][0]["sCode"] == "0"
        assert payload["data"][0]["clOrdId"] == "sdkTEST0001"
        # Order must be in the store. / 订单必须已写入 store。
        assert mock.store.get_by_cl_ord_id("BTC-USDT-SWAP", "sdkTEST0001") is not None


def test_bad_signature_returns_50113() -> None:
    run(_bad_signature_returns_50113())


async def _bad_signature_returns_50113() -> None:
    async with run_mock_okx() as mock:
        body = json.dumps({"x": 1})
        headers = _signed_headers(
            method="POST",
            request_path="/api/v5/trade/order",
            body=body,
            api_key=mock.api_key,
            api_secret="WRONG-SECRET",
            passphrase=mock.passphrase,
            demo=mock.demo,
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{mock.base_url}/api/v5/trade/order",
                data=body,
                headers=headers,
            ) as resp:
                payload = await resp.json()
        assert payload["code"] == "50113"


def test_fault_inject_5xx_does_not_persist_order() -> None:
    run(_fault_inject_5xx_does_not_persist_order())


async def _fault_inject_5xx_does_not_persist_order() -> None:
    async with run_mock_okx() as mock:
        mock.faults.inject_5xx = True
        body = _build_place_body("sdkTEST5xx0")
        headers = _signed_headers_for_place(mock, body)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{mock.base_url}/api/v5/trade/order",
                data=body,
                headers=headers,
            ) as resp:
                assert resp.status == 503
        # No order should exist. / 订单不应被写入。
        assert mock.store.get_by_cl_ord_id("BTC-USDT-SWAP", "sdkTEST5xx0") is None


def test_fault_place_succeeds_internally_but_returns_5xx() -> None:
    run(_fault_place_succeeds_internally_but_returns_5xx())


async def _fault_place_succeeds_internally_but_returns_5xx() -> None:
    """The killer fault: order IS placed but client gets 5xx.

    关键故障：订单已落地，但客户端收到 5xx。
    """
    async with run_mock_okx() as mock:
        mock.faults.place_succeeds_internally_but_returns_5xx = True
        body = _build_place_body("sdkTESTHALF")
        headers = _signed_headers_for_place(mock, body)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{mock.base_url}/api/v5/trade/order",
                data=body,
                headers=headers,
            ) as resp:
                assert resp.status == 503
        # Order MUST be in the store, ready for reconciliation.
        # 订单必须已写入 store，等待 reconciliation 找到它。
        order = mock.store.get_by_cl_ord_id("BTC-USDT-SWAP", "sdkTESTHALF")
        assert order is not None
        assert order.state == "live"


def test_query_returns_51603_for_first_n_then_resolves() -> None:
    run(_query_returns_51603_for_first_n_then_resolves())


async def _query_returns_51603_for_first_n_then_resolves() -> None:
    async with run_mock_okx() as mock:
        # First, place an order normally.
        body = _build_place_body("sdkTESTRACE")
        headers = _signed_headers_for_place(mock, body)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{mock.base_url}/api/v5/trade/order",
                data=body,
                headers=headers,
            ) as resp:
                payload = await resp.json()
                assert payload["code"] == "0"

            # Arm the race: next 2 query-by-clOrdId requests fake 51603.
            mock.faults.query_returns_51603_for_first_n = 2

            for expected_code in ("51603", "51603", "0"):
                path = "/api/v5/trade/order" "?instId=BTC-USDT-SWAP&clOrdId=sdkTESTRACE"
                headers = _signed_headers(
                    method="GET",
                    request_path=path,
                    body="",
                    api_key=mock.api_key,
                    api_secret=mock.api_secret,
                    passphrase=mock.passphrase,
                    demo=mock.demo,
                )
                async with session.get(
                    f"{mock.base_url}{path}", headers=headers
                ) as resp:
                    payload = await resp.json()
                assert payload["code"] == expected_code, payload


def test_inject_429_returns_rate_limit() -> None:
    run(_inject_429_returns_rate_limit())


async def _inject_429_returns_rate_limit() -> None:
    async with run_mock_okx() as mock:
        mock.faults.inject_429 = True
        body = _build_place_body("sdkTEST429X")
        headers = _signed_headers_for_place(mock, body)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{mock.base_url}/api/v5/trade/order",
                data=body,
                headers=headers,
            ) as resp:
                assert resp.status == 429
                payload = await resp.json()
        assert payload["code"] == "50011"


def test_apply_once_resets_after_first_hit() -> None:
    run(_apply_once_resets_after_first_hit())


async def _apply_once_resets_after_first_hit() -> None:
    async with run_mock_okx() as mock:
        mock.faults.inject_5xx = True
        mock.faults.apply_once = True

        async with aiohttp.ClientSession() as session:
            # First request: 5xx.
            body = _build_place_body("sdkTESTONE1")
            headers = _signed_headers_for_place(mock, body)
            async with session.post(
                f"{mock.base_url}/api/v5/trade/order",
                data=body,
                headers=headers,
            ) as resp:
                assert resp.status == 503

            # Faults should be cleared. Second request: success.
            assert mock.faults.inject_5xx is False
            body = _build_place_body("sdkTESTONE2")
            headers = _signed_headers_for_place(mock, body)
            async with session.post(
                f"{mock.base_url}/api/v5/trade/order",
                data=body,
                headers=headers,
            ) as resp:
                payload = await resp.json()
        assert payload["code"] == "0"


def test_drop_response_triggers_client_timeout() -> None:
    run(_drop_response_triggers_client_timeout())


async def _drop_response_triggers_client_timeout() -> None:
    async with run_mock_okx() as mock:
        mock.faults.drop_response = True
        body = _build_place_body("sdkTESTDROP")
        headers = _signed_headers_for_place(mock, body)
        timeout = aiohttp.ClientTimeout(total=0.5)
        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{mock.base_url}/api/v5/trade/order",
                    data=body,
                    headers=headers,
                ) as resp:
                    await resp.read()


def test_reset_endpoint_clears_state_and_faults() -> None:
    run(_reset_endpoint_clears_state_and_faults())


async def _reset_endpoint_clears_state_and_faults() -> None:
    async with run_mock_okx() as mock:
        # Place an order and arm a fault.
        body = _build_place_body("sdkTESTRSET")
        headers = _signed_headers_for_place(mock, body)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{mock.base_url}/api/v5/trade/order",
                data=body,
                headers=headers,
            ) as resp:
                assert (await resp.json())["code"] == "0"

            mock.faults.inject_5xx = True

            async with session.post(f"{mock.base_url}/_mock/reset") as resp:
                assert resp.status == 200

        assert mock.faults.inject_5xx is False
        assert mock.store.get_by_cl_ord_id("BTC-USDT-SWAP", "sdkTESTRSET") is None
