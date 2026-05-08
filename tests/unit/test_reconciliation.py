from asyncio import run
from decimal import Decimal

import pytest

from okx_perp_reliable.client import ReliablePerpClient
from okx_perp_reliable.enums import OrderSide, OrderStatus, OrderType, ResultStatus
from okx_perp_reliable.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
    OrderNotFoundError,
    UnknownStateError,
)
from okx_perp_reliable.reconciliation import OrderReconciler


async def _no_sleep(_: float) -> None:
    return None


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def request(self, method, path, *, params=None, json_body=None):
        self.calls.append((method, path, params, json_body))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_reconcile_confirmed_order() -> None:
    run(_test_reconcile_confirmed_order())


async def _test_reconcile_confirmed_order() -> None:
    http = FakeHttp(
        [
            {
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "clOrdId": "sdkABC123",
                        "ordId": "1",
                        "state": "filled",
                        "accFillSz": "0.01",
                        "avgPx": "65000",
                    }
                ],
            }
        ]
    )
    reconciler = OrderReconciler(http_client=http, sleep=_no_sleep)

    result = await reconciler.reconcile(inst_id="BTC-USDT-SWAP", cl_ord_id="sdkABC123")

    assert result.status == ResultStatus.CONFIRMED
    assert result.order_status == OrderStatus.FILLED
    assert result.reconciliation_attempts == 1


def test_reconcile_order_not_found_is_failed() -> None:
    run(_test_reconcile_order_not_found_is_failed())


async def _test_reconcile_order_not_found_is_failed() -> None:
    http = FakeHttp([{"code": "51603", "msg": "Order does not exist", "data": []}])
    reconciler = OrderReconciler(http_client=http, sleep=_no_sleep)

    result = await reconciler.reconcile(inst_id="BTC-USDT-SWAP", cl_ord_id="sdkABC123")

    assert result.status == ResultStatus.FAILED
    assert isinstance(result.error, OrderNotFoundError)


def test_reconcile_network_errors_become_unknown() -> None:
    run(_test_reconcile_network_errors_become_unknown())


async def _test_reconcile_network_errors_become_unknown() -> None:
    http = FakeHttp(
        [
            NetworkError("timeout"),
            NetworkError("timeout"),
            NetworkError("timeout"),
        ]
    )
    reconciler = OrderReconciler(http_client=http, sleep=_no_sleep, max_attempts=3)

    result = await reconciler.reconcile(inst_id="BTC-USDT-SWAP", cl_ord_id="sdkABC123")

    assert result.status == ResultStatus.UNKNOWN
    assert result.reconciliation_attempts == 3
    assert isinstance(result.error, UnknownStateError)


def test_reconcile_51603_returns_failed_when_grace_is_zero() -> None:
    """Pin default 51603 behavior as immediate FAILED.

    固定默认 51603 行为：立即返回 FAILED。
    """
    run(_test_reconcile_51603_returns_failed_when_grace_is_zero())


async def _test_reconcile_51603_returns_failed_when_grace_is_zero() -> None:
    """Run default zero-grace 51603 reconciliation. / 执行默认零宽限 51603 确认。"""
    http = FakeHttp(
        [
            {"code": "51603", "msg": "Order does not exist", "data": []},
            {
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "clOrdId": "sdkABC123",
                        "ordId": "1",
                        "state": "live",
                    }
                ],
            },
        ]
    )
    reconciler = OrderReconciler(http_client=http, sleep=_no_sleep)

    result = await reconciler.reconcile(inst_id="BTC-USDT-SWAP", cl_ord_id="sdkABC123")

    assert result.status == ResultStatus.FAILED
    assert result.reconciliation_attempts == 1
    assert isinstance(result.error, OrderNotFoundError)
    assert len(http.calls) == 1


def test_reconcile_51603_resolves_within_grace_window() -> None:
    """Verify opt-in 51603 grace can resolve to CONFIRMED.

    验证可选 51603 宽限窗口可最终确认订单。
    """
    run(_test_reconcile_51603_resolves_within_grace_window())


async def _test_reconcile_51603_resolves_within_grace_window() -> None:
    """Run 51603 once, then successful query. / 先返回一次 51603，再查单成功。"""
    http = FakeHttp(
        [
            {"code": "51603", "msg": "Order does not exist", "data": []},
            {
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "clOrdId": "sdkABC123",
                        "ordId": "1",
                        "state": "live",
                    }
                ],
            },
        ]
    )
    reconciler = OrderReconciler(
        http_client=http,
        sleep=_no_sleep,
        reconciliation_51603_grace_seconds=5.0,
    )

    result = await reconciler.reconcile(inst_id="BTC-USDT-SWAP", cl_ord_id="sdkABC123")

    assert result.status == ResultStatus.CONFIRMED
    assert result.reconciliation_attempts >= 2
    assert result.order_status == OrderStatus.LIVE


def test_reconcile_51603_persistent_returns_failed_under_grace() -> None:
    """Verify persistent 51603 still returns FAILED under grace.

    验证持续 51603 在宽限窗口下仍会返回 FAILED。
    """
    run(_test_reconcile_51603_persistent_returns_failed_under_grace())


async def _test_reconcile_51603_persistent_returns_failed_under_grace() -> None:
    """Run persistent 51603 responses. / 执行持续 51603 响应场景。"""
    http = FakeHttp(
        [
            {"code": "51603", "msg": "Order does not exist", "data": []},
            {"code": "51603", "msg": "Order does not exist", "data": []},
            {"code": "51603", "msg": "Order does not exist", "data": []},
            {"code": "51603", "msg": "Order does not exist", "data": []},
        ]
    )
    reconciler = OrderReconciler(
        http_client=http,
        sleep=_no_sleep,
        max_attempts=3,
        reconciliation_51603_grace_seconds=5.0,
    )

    result = await reconciler.reconcile(inst_id="BTC-USDT-SWAP", cl_ord_id="sdkABC123")

    assert result.status == ResultStatus.FAILED
    assert result.reconciliation_attempts == 3
    assert isinstance(result.error, OrderNotFoundError)


def test_grace_seconds_must_not_exceed_reconciliation_timeout() -> None:
    """Validate grace window cannot exceed total reconciliation timeout.

    验证 51603 宽限窗口不能超过总 reconciliation 超时。
    """
    with pytest.raises(ConfigurationError):
        ReliablePerpClient(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            reconciliation_timeout=1.0,
            reconciliation_51603_grace_seconds=2.0,
        )


def test_grace_seconds_must_not_be_negative() -> None:
    """Validate grace window cannot be negative.

    验证 51603 宽限窗口不能为负数。
    """
    with pytest.raises(ConfigurationError):
        ReliablePerpClient(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            reconciliation_51603_grace_seconds=-1.0,
        )


def test_50113_raises_authentication_error() -> None:
    """Verify auth-class sCode 50113 raises AuthenticationError.

    验证鉴权类 sCode 50113 会抛出 AuthenticationError。
    """
    run(_test_50113_raises_authentication_error())


async def _test_50113_raises_authentication_error() -> None:
    """Run a place response with 50113. / 执行 50113 下单响应场景。"""
    client = ReliablePerpClient(
        api_key="key",
        api_secret="secret",
        passphrase="pass",
        http_client=FakeHttp(
            [{"code": "50113", "msg": "Invalid signature", "data": []}]
        ),
    )

    with pytest.raises(AuthenticationError) as excinfo:
        await client.place_order(
            inst_id="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("1"),
            price=Decimal("10000"),
        )

    assert excinfo.value.okx_code == "50113"


def test_50114_raises_authentication_error() -> None:
    """Verify auth-class sCode 50114 raises AuthenticationError.

    验证鉴权类 sCode 50114 会抛出 AuthenticationError。
    """
    run(_test_50114_raises_authentication_error())


async def _test_50114_raises_authentication_error() -> None:
    """Run a place response with 50114. / 执行 50114 下单响应场景。"""
    client = ReliablePerpClient(
        api_key="key",
        api_secret="secret",
        passphrase="pass",
        http_client=FakeHttp(
            [{"code": "50114", "msg": "Invalid passphrase", "data": []}]
        ),
    )

    with pytest.raises(AuthenticationError) as excinfo:
        await client.place_order(
            inst_id="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("1"),
            price=Decimal("10000"),
        )

    assert excinfo.value.okx_code == "50114"
