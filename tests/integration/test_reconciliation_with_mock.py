from asyncio import run
from decimal import Decimal

import pytest
from tests.integration._helpers import mock_and_client

from okx_perp_reliable import (
    AuthenticationError,
    OrderNotFoundError,
    OrderSide,
    OrderStatus,
    OrderType,
    RateLimitError,
    ResultStatus,
)


def test_reconcile_after_5xx_with_order_inserted() -> None:
    """Verify reconciliation confirms an inserted order after HTTP 5xx.

    验证下单已落地但 HTTP 5xx 时 reconciliation 能确认订单。
    """
    run(_test_reconcile_after_5xx_with_order_inserted())


async def _test_reconcile_after_5xx_with_order_inserted() -> None:
    """Run the 5xx-after-insert mock scenario. / 执行已落地后 5xx 场景。"""
    async with mock_and_client() as (mock, client):
        mock.faults.place_succeeds_internally_but_returns_5xx = True

        result = await client.place_order(
            inst_id="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("1"),
            price=Decimal("10000"),
            pos_side="long",
            td_mode="cross",
        )

        stored = mock.store.get_by_cl_ord_id("BTC-USDT-SWAP", result.cl_ord_id)

    assert result.status is ResultStatus.CONFIRMED
    assert result.order_status in {
        OrderStatus.LIVE,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
    }
    assert result.order_status is OrderStatus.LIVE
    assert result.cl_ord_id.startswith("sdk")
    assert result.reconciliation_attempts >= 1
    assert result.error is None
    assert stored is not None
    assert stored.cl_ord_id == result.cl_ord_id
    assert stored.ord_id == result.order_id


def test_place_order_429_raises_rate_limit_error() -> None:
    """Verify HTTP 429 propagates as RateLimitError.

    验证 HTTP 429 会以 RateLimitError 形式抛出。
    """
    run(_test_place_order_429_raises_rate_limit_error())


async def _test_place_order_429_raises_rate_limit_error() -> None:
    """Run the 429 mock scenario. / 执行 429 限频场景。"""
    async with mock_and_client() as (mock, client):
        mock.faults.inject_429 = True
        with pytest.raises(RateLimitError):
            await client.place_order(
                inst_id="BTC-USDT-SWAP",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                size=Decimal("1"),
                price=Decimal("10000"),
                td_mode="cross",
                pos_side="long",
            )

        assert mock.store.all_orders() == []


def test_place_order_clock_drift_raises_authentication_error() -> None:
    """Verify drifted timestamps surface as AuthenticationError.

    验证时间戳漂移会暴露为 AuthenticationError。
    """
    run(_test_place_order_clock_drift_raises_authentication_error())


async def _test_place_order_clock_drift_raises_authentication_error() -> None:
    """Run the tight timestamp-window scenario. / 执行严格时间戳窗口场景。"""
    async with mock_and_client() as (mock, client):
        # Tighten the timestamp window so any wall-clock latency triggers 50112.
        # 把时间戳窗口收得极窄，任何挂钟延迟都会触发 50112。
        mock.faults.enforce_timestamp_window_seconds = 0.0001

        with pytest.raises(AuthenticationError) as excinfo:
            await client.place_order(
                inst_id="BTC-USDT-SWAP",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                size=Decimal("1"),
                price=Decimal("10000"),
                td_mode="cross",
                pos_side="long",
            )

        # Must preserve the OKX sCode for diagnosability.
        # 必须保留 OKX sCode 以便排查。
        assert excinfo.value.okx_code == "50112"
        assert mock.store.all_orders() == []


def test_reconcile_after_drop_with_order_inserted() -> None:
    """Verify reconciliation confirms an inserted order after response drop.

    验证下单已落地但响应丢失时 reconciliation 能确认订单。
    """
    run(_test_reconcile_after_drop_with_order_inserted())


async def _test_reconcile_after_drop_with_order_inserted() -> None:
    """Run the drop-after-insert mock scenario. / 执行已落地后响应丢失场景。"""
    async with mock_and_client() as (mock, client):
        mock.faults.place_drops_response = True

        result = await client.place_order(
            inst_id="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("1"),
            price=Decimal("10000"),
            pos_side="long",
            td_mode="cross",
        )

        stored = mock.store.get_by_cl_ord_id("BTC-USDT-SWAP", result.cl_ord_id)

    assert result.status is ResultStatus.CONFIRMED
    assert result.order_status in {
        OrderStatus.LIVE,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
    }
    assert result.order_status is OrderStatus.LIVE
    assert result.cl_ord_id.startswith("sdk")
    assert result.reconciliation_attempts >= 1
    assert result.error is None
    assert stored is not None
    assert stored.cl_ord_id == result.cl_ord_id
    assert stored.ord_id == result.order_id


def test_51603_default_config_immediately_returns_failed_under_option_c() -> None:
    """Verify default Option C config keeps immediate 51603 failure.

    验证 Option C 默认配置保持 51603 立即失败。
    """
    run(_test_51603_default_config_immediately_returns_failed_under_option_c())


async def _test_51603_default_config_immediately_returns_failed_under_option_c() -> (
    None
):
    """Run 51603 race with default zero grace. / 使用默认零宽限执行 51603 竞态。"""
    async with mock_and_client() as (mock, client):
        mock.faults.place_succeeds_internally_but_returns_5xx = True
        mock.faults.query_returns_51603_for_first_n = 1

        result = await client.place_order(
            inst_id="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("1"),
            price=Decimal("10000"),
            td_mode="cross",
            pos_side="long",
        )

        live_order = mock.store.get_by_cl_ord_id("BTC-USDT-SWAP", result.cl_ord_id)

    assert result.status is ResultStatus.FAILED
    assert isinstance(result.error, OrderNotFoundError)
    assert live_order is not None


def test_51603_grace_config_retries_until_confirmed_under_option_c() -> None:
    """Verify opt-in Option C grace retries through a 51603 race.

    验证 Option C 可选宽限会重试并穿过 51603 竞态。
    """
    run(_test_51603_grace_config_retries_until_confirmed_under_option_c())


async def _test_51603_grace_config_retries_until_confirmed_under_option_c() -> None:
    """Run 51603 race with enabled grace.

    使用启用的宽限窗口执行 51603 竞态。
    """
    async with mock_and_client(
        reconciliation_51603_grace_seconds=5.0,
    ) as (mock, client):
        mock.faults.place_succeeds_internally_but_returns_5xx = True
        mock.faults.query_returns_51603_for_first_n = 2

        result = await client.place_order(
            inst_id="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("1"),
            price=Decimal("10000"),
            td_mode="cross",
            pos_side="long",
        )

    assert result.status is ResultStatus.CONFIRMED
    assert result.order_status is OrderStatus.LIVE
    assert result.reconciliation_attempts >= 3
    assert result.error is None


def test_51603_grace_config_persistent_returns_failed_under_option_c() -> None:
    """Verify persistent 51603 still fails with opt-in Option C grace.

    验证 Option C 可选宽限下持续 51603 仍会失败。
    """
    run(_test_51603_grace_config_persistent_returns_failed_under_option_c())


async def _test_51603_grace_config_persistent_returns_failed_under_option_c() -> None:
    """Run a 51603 race longer than grace. / 执行长于宽限窗口的 51603 竞态。"""
    async with mock_and_client(
        reconciliation_timeout=2.0,
        reconciliation_51603_grace_seconds=0.2,
    ) as (mock, client):
        mock.faults.place_succeeds_internally_but_returns_5xx = True
        mock.faults.query_returns_51603_for_first_n = 1000

        result = await client.place_order(
            inst_id="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("1"),
            price=Decimal("10000"),
            td_mode="cross",
            pos_side="long",
        )

    assert result.status is ResultStatus.FAILED
    assert isinstance(result.error, OrderNotFoundError)
