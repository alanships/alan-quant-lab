"""Standard SDK exception hierarchy. / SDK 标准异常体系。"""


class ReliableSdkError(Exception):
    """Base SDK error. / SDK 异常基类。"""

    def __init__(
        self,
        message: str,
        *,
        okx_code: str | None = None,
        raw_response: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.okx_code = okx_code
        self.raw_response = raw_response


class ConfigurationError(ReliableSdkError):
    """Invalid SDK configuration. / SDK 配置错误。"""


class AuthenticationError(ReliableSdkError):
    """Invalid OKX API authentication. / OKX API 鉴权失败。"""


class InsufficientFundsError(ReliableSdkError):
    """Insufficient account balance or margin. / 账户余额或保证金不足。"""


class InvalidOrderError(ReliableSdkError):
    """Invalid order parameters. / 订单参数无效。"""


class OrderNotFoundError(ReliableSdkError):
    """Order cannot be found on OKX. / OKX 未找到该订单。"""


class RateLimitError(ReliableSdkError):
    """OKX rate limit was reached. / 触发 OKX 频率限制。"""


class PositionError(ReliableSdkError):
    """Position mode or position constraint error. / 仓位模式或仓位约束错误。"""


class ExchangeMaintenanceError(ReliableSdkError):
    """OKX endpoint or system is unavailable. / OKX 接口或系统不可用。"""


class UnknownStateError(ReliableSdkError):
    """Order state is unknown after reconciliation.

    查单后仍无法确认订单状态。
    """


class NetworkError(ReliableSdkError):
    """Network, timeout, or retryable transport error. / 网络、超时或可重试传输错误。"""
