"""OKX error-code mapping. / OKX 错误码映射。"""

from okx_perp_reliable.exceptions import (
    AuthenticationError,
    ExchangeMaintenanceError,
    InsufficientFundsError,
    InvalidOrderError,
    NetworkError,
    OrderNotFoundError,
    PositionError,
    RateLimitError,
    ReliableSdkError,
)

ERROR_CODE_TO_EXCEPTION: dict[str, type[ReliableSdkError]] = {
    "1": ReliableSdkError,
    "50001": NetworkError,
    "50004": NetworkError,
    "50005": ExchangeMaintenanceError,
    "50006": InvalidOrderError,
    "50013": NetworkError,
    "50026": ExchangeMaintenanceError,
    "50040": NetworkError,
    "50061": RateLimitError,
    "50101": AuthenticationError,
    "50102": AuthenticationError,
    "50103": AuthenticationError,
    "50104": AuthenticationError,
    "50105": AuthenticationError,
    "50106": AuthenticationError,
    "50107": AuthenticationError,
    "50108": AuthenticationError,
    "50109": AuthenticationError,
    "50110": AuthenticationError,
    "50011": RateLimitError,
    "50111": AuthenticationError,
    "50112": AuthenticationError,
    "50113": AuthenticationError,
    "50114": AuthenticationError,
    "51000": InvalidOrderError,
    "51001": InvalidOrderError,
    "51002": InvalidOrderError,
    "51003": InvalidOrderError,
    "51008": InsufficientFundsError,
    "51008_1000": InsufficientFundsError,
    "51008_1001": InsufficientFundsError,
    "51020": InvalidOrderError,
    "51024": InvalidOrderError,
    "51120": InsufficientFundsError,
    "51400": OrderNotFoundError,
    "51603": OrderNotFoundError,
}

DEFAULT_EXCEPTION = ReliableSdkError
RAISE_ERROR_CODES = frozenset({"50111", "50112", "50113", "50114"})


def classify_error_code(code: str) -> type[ReliableSdkError]:
    """Return SDK exception class for an OKX code. / 返回 OKX 错误码对应的异常类。"""
    if code == "0":
        return DEFAULT_EXCEPTION
    if code.startswith("51008"):
        return InsufficientFundsError
    if code.startswith("51004"):
        return PositionError
    if code.startswith("501"):
        return AuthenticationError
    if code.startswith("5"):
        return ERROR_CODE_TO_EXCEPTION.get(code, ExchangeMaintenanceError)
    return ERROR_CODE_TO_EXCEPTION.get(code, DEFAULT_EXCEPTION)


def build_error(
    code: str,
    message: str,
    *,
    raw_response: dict | None = None,
) -> ReliableSdkError:
    """Build mapped SDK error instance. / 创建映射后的 SDK 异常实例。"""
    error_cls = classify_error_code(code)
    return error_cls(
        message or f"OKX error {code}",
        okx_code=code,
        raw_response=raw_response,
    )


def should_raise_error(error: ReliableSdkError) -> bool:
    """Return whether a mapped SDK error should be raised.

    返回映射后的 SDK 错误是否应直接抛出。
    """
    return error.okx_code in RAISE_ERROR_CODES
