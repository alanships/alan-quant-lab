"""Enums for the public order API. / 公开下单 API 的枚举定义。"""

from enum import StrEnum


class ResultStatus(StrEnum):
    """Final SDK result status. / SDK 返回的最终状态。"""

    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class OrderStatus(StrEnum):
    """OKX order lifecycle state. / OKX 订单生命周期状态。"""

    LIVE = "live"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    MMP_CANCELED = "mmp_canceled"


class OrderSide(StrEnum):
    """Order side. / 买卖方向。"""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Supported OKX order type for v1. / v1 支持的 OKX 订单类型。"""

    MARKET = "market"
    LIMIT = "limit"
