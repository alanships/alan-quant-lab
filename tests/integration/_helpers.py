"""Shared helpers for integration tests against the mock OKX server.

集成测试与 mock OKX 服务器对接的共享工具。
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from tests.mock import MockOkxServer, run_mock_okx

from okx_perp_reliable import ReliablePerpClient


@contextlib.asynccontextmanager
async def mock_and_client(
    *,
    timeout: float = 1.0,
    reconciliation_timeout: float = 5.0,
    reconciliation_max_attempts: int = 3,
    reconciliation_51603_grace_seconds: float = 0.0,
) -> AsyncIterator[tuple[MockOkxServer, ReliablePerpClient]]:
    """Start the mock and a configured client targeting it.

    启动 mock 并构造一个直接指向它的客户端。

    Defaults are tuned for fast tests: short HTTP timeout, short
    reconciliation budget.
    默认值面向快速测试：较短 HTTP 超时和较短 reconciliation 预算。
    """
    async with run_mock_okx() as mock:
        client = ReliablePerpClient(
            api_key=mock.api_key,
            api_secret=mock.api_secret,
            passphrase=mock.passphrase,
            demo=mock.demo,
            timeout=timeout,
            reconciliation_timeout=reconciliation_timeout,
            reconciliation_max_attempts=reconciliation_max_attempts,
            reconciliation_51603_grace_seconds=reconciliation_51603_grace_seconds,
            base_url=mock.base_url,
        )
        try:
            yield mock, client
        finally:
            await client.close()
