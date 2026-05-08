"""In-process mock of OKX v5 REST API for fault-injection testing.

OKX v5 REST API 的进程内 mock 实现，用于故障注入测试。

This package is **not** part of the published SDK. It is a test fixture
that lets the SDK be exercised against deterministic, scriptable failure
modes (timeouts, 5xx with order placed, 51603 race, 429, clock drift, …)
without touching the real exchange.

本包不属于发布的 SDK，仅作为测试夹具使用，让 SDK 在确定性的、可编排的
故障模式下被验证（超时、5xx 但订单已落地、51603 竞态、429、时钟漂移……），
无需触碰真实交易所。

Typical usage in a pytest test (typical CI pattern):

    async with run_mock_okx() as mock:
        mock.faults.place_succeeds_internally_but_returns_5xx = True
        client = build_sdk_client(base_url=mock.base_url, ...)
        result = await client.place_order(...)
        assert result.status is ResultStatus.CONFIRMED
        assert result.reconciliation_attempts >= 1
"""

from tests.mock.faults import FaultConfig
from tests.mock.server import MockOkxServer, run_mock_okx
from tests.mock.state import MockOrder, OrderStore

__all__ = [
    "FaultConfig",
    "MockOkxServer",
    "MockOrder",
    "OrderStore",
    "run_mock_okx",
]
