import os
from asyncio import run
from decimal import Decimal

import pytest

from okx_perp_reliable import OrderSide, OrderType, ReliablePerpClient, ResultStatus
from okx_perp_reliable.http import OkxHttpClient


def _has_demo_credentials() -> bool:
    return all(
        os.getenv(name) for name in ["OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"]
    )


@pytest.mark.skipif(
    not _has_demo_credentials(),
    reason="OKX demo trading credentials are not available",
)
def test_demo_market_order_and_query() -> None:
    run(_test_demo_market_order_and_query())


async def _test_demo_market_order_and_query() -> None:
    inst_id = os.getenv("OKX_E2E_INST_ID", "BTC-USDT-SWAP")
    pos_side = os.getenv("OKX_E2E_POS_SIDE", "long")
    size = Decimal(os.getenv("OKX_E2E_SIZE", "1"))
    client = ReliablePerpClient(
        api_key=os.environ["OKX_API_KEY"],
        api_secret=os.environ["OKX_API_SECRET"],
        passphrase=os.environ["OKX_PASSPHRASE"],
        demo=True,
        timeout=30,
    )
    try:
        result = await client.place_order(
            inst_id=inst_id,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=size,
            td_mode="cross",
            pos_side=pos_side,
        )
        assert result.status == ResultStatus.CONFIRMED
        assert result.order_id

        payload = await client.http_client.request(
            "GET",
            "/api/v5/trade/order",
            params={"instId": inst_id, "clOrdId": result.cl_ord_id},
        )
        assert payload["code"] == "0"
        data = payload["data"][0]
        assert data["clOrdId"] == result.cl_ord_id
        assert data["ordId"] == result.order_id
        assert data["state"] in {"live", "partially_filled", "filled"}
    finally:
        await client.close()


@pytest.mark.skipif(
    not _has_demo_credentials(),
    reason="OKX demo trading credentials are not available",
)
def test_demo_private_balance() -> None:
    run(_test_demo_private_balance())


async def _test_demo_private_balance() -> None:
    client = OkxHttpClient(
        api_key=os.environ["OKX_API_KEY"],
        api_secret=os.environ["OKX_API_SECRET"],
        passphrase=os.environ["OKX_PASSPHRASE"],
        demo=True,
        timeout=30,
    )
    try:
        payload = await client.request("GET", "/api/v5/account/balance")
        assert payload["code"] == "0"
        assert payload["data"]
    finally:
        await client.close()
