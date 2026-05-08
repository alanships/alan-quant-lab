from okx_perp_reliable._internal.error_mapping import classify_error_code
from okx_perp_reliable.exceptions import (
    AuthenticationError,
    ExchangeMaintenanceError,
    InsufficientFundsError,
    InvalidOrderError,
    NetworkError,
    OrderNotFoundError,
    PositionError,
    RateLimitError,
)


def test_seed_error_mapping_from_plan_and_docs() -> None:
    assert classify_error_code("50001") is NetworkError
    assert classify_error_code("50004") is NetworkError
    assert classify_error_code("50011") is RateLimitError
    assert classify_error_code("50061") is RateLimitError
    assert classify_error_code("50101") is AuthenticationError
    assert classify_error_code("50102") is AuthenticationError
    assert classify_error_code("50103") is AuthenticationError
    assert classify_error_code("50104") is AuthenticationError
    assert classify_error_code("50105") is AuthenticationError
    assert classify_error_code("50106") is AuthenticationError
    assert classify_error_code("50107") is AuthenticationError
    assert classify_error_code("50108") is AuthenticationError
    assert classify_error_code("50109") is AuthenticationError
    assert classify_error_code("50110") is AuthenticationError
    assert classify_error_code("50111") is AuthenticationError
    assert classify_error_code("50112") is AuthenticationError
    assert classify_error_code("50113") is AuthenticationError
    assert classify_error_code("50114") is AuthenticationError
    assert classify_error_code("51000") is InvalidOrderError
    assert classify_error_code("51001") is InvalidOrderError
    assert classify_error_code("51002") is InvalidOrderError
    assert classify_error_code("51003") is InvalidOrderError
    assert classify_error_code("51004_1101") is PositionError
    assert classify_error_code("51008") is InsufficientFundsError
    assert classify_error_code("51008_1000") is InsufficientFundsError
    assert classify_error_code("51020") is InvalidOrderError
    assert classify_error_code("51120") is InsufficientFundsError
    assert classify_error_code("51400") is OrderNotFoundError
    assert classify_error_code("51603") is OrderNotFoundError
    assert classify_error_code("59999") is ExchangeMaintenanceError
