"""Error handling example. / 异常处理示例。"""

from okx_perp_reliable import (
    AuthenticationError,
    InsufficientFundsError,
    InvalidOrderError,
    RateLimitError,
    ResultStatus,
)


def inspect_failure(result) -> None:
    """Inspect a failed order result. / 检查失败下单结果。"""
    if result.status != ResultStatus.FAILED:
        return

    if isinstance(result.error, InsufficientFundsError):
        print("balance or margin is insufficient")
    elif isinstance(result.error, InvalidOrderError):
        print("order parameters were rejected by OKX")
    elif isinstance(result.error, AuthenticationError):
        print("API key, secret, passphrase, or demo/prod environment is invalid")
    elif isinstance(result.error, RateLimitError):
        print("request was rate limited")
    else:
        print(f"order failed: {result.error}")
