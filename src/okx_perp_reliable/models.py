"""Pydantic data models. / Pydantic 数据模型。"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from okx_perp_reliable.enums import OrderSide, OrderStatus, OrderType, ResultStatus
from okx_perp_reliable.exceptions import ReliableSdkError


class OrderRequest(BaseModel):
    """Order placement request. / 下单请求模型。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    inst_id: str = Field(..., description="OKX instrument ID, e.g. BTC-USDT-SWAP.")
    side: OrderSide
    order_type: OrderType
    size: Decimal = Field(..., gt=Decimal("0"))
    cl_ord_id: str | None = Field(default=None, max_length=32)
    price: Decimal | None = Field(default=None, gt=Decimal("0"))
    pos_side: Literal["long", "short", "net"] | None = None
    td_mode: Literal["cross", "isolated"] = "cross"
    reduce_only: bool = False

    @model_validator(mode="after")
    def validate_limit_price(self) -> "OrderRequest":
        """Require price for LIMIT orders. / LIMIT 单必须提供价格。"""
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("price is required for LIMIT orders")
        return self


class OrderResult(BaseModel):
    """Unified order result. / 统一下单结果模型。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: ResultStatus
    order_status: OrderStatus | None = None
    order_id: str | None = None
    cl_ord_id: str
    inst_id: str
    filled_size: Decimal | None = None
    avg_price: Decimal | None = None
    raw_response: dict[str, Any] | None = None
    reconciliation_attempts: int = Field(default=0, ge=0)
    error: ReliableSdkError | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
