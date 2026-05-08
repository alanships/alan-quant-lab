from decimal import Decimal

import pytest

from okx_perp_reliable.enums import OrderSide, OrderType, ResultStatus
from okx_perp_reliable.models import OrderRequest, OrderResult


def test_limit_order_requires_price() -> None:
    with pytest.raises(ValueError):
        OrderRequest(
            inst_id="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("0.01"),
        )


def test_order_result_skeleton_accepts_unknown() -> None:
    result = OrderResult(
        status=ResultStatus.UNKNOWN,
        cl_ord_id="sdkABC123",
        inst_id="BTC-USDT-SWAP",
    )

    assert result.status == ResultStatus.UNKNOWN
    assert result.reconciliation_attempts == 0
