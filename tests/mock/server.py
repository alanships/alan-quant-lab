"""Aiohttp-based mock OKX server with start/stop helpers.

基于 aiohttp 的 mock OKX 服务器，含启停辅助。

The server runs in-process on an OS-assigned port and exposes:

进程内运行，自动分配端口，对外暴露：

* ``base_url``  e.g. ``http://127.0.0.1:54321``
* ``faults``    a :class:`FaultConfig` whose attributes can be flipped at any time
* ``store``     an :class:`OrderStore` for direct test inspection
* ``api_key`` / ``api_secret`` / ``passphrase``  the credentials the SDK
  must present (defaults below match the demo trading docs).

A typical test:

    async with run_mock_okx() as mock:
        mock.faults.place_succeeds_internally_but_returns_5xx = True
        ...

"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

from aiohttp import web

from tests.mock.routes import (
    MockServerState,
    handle_cancel_order,
    handle_inject_fill,
    handle_place_order,
    handle_public_time,
    handle_query_order,
    handle_reset,
    handle_set_faults,
)
from tests.mock.state import OrderStore


@dataclass
class MockOkxServer:
    """Handle to a running mock server. / 已启动 mock 服务的句柄。"""

    base_url: str
    state: MockServerState
    runner: web.AppRunner
    site: web.TCPSite

    @property
    def faults(self):
        return self.state.faults

    @property
    def store(self) -> OrderStore:
        return self.state.store

    @property
    def api_key(self) -> str:
        return self.state.api_key

    @property
    def api_secret(self) -> str:
        return self.state.api_secret

    @property
    def passphrase(self) -> str:
        return self.state.passphrase

    @property
    def demo(self) -> bool:
        return self.state.demo

    async def aclose(self) -> None:
        """Stop the server. / 停止服务。"""
        await self.site.stop()
        await self.runner.cleanup()


def build_app(
    *,
    api_key: str = "mock-api-key",
    api_secret: str = "mock-api-secret",
    passphrase: str = "mock-passphrase",
    demo: bool = True,
) -> tuple[web.Application, MockServerState]:
    """Construct the aiohttp app and shared state.

    构造 aiohttp 应用以及共享状态。
    """
    app = web.Application()
    state = MockServerState(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        demo=demo,
    )
    app["state"] = state

    # Real OKX endpoints. / 真实 OKX 端点。
    app.router.add_get("/api/v5/public/time", handle_public_time)
    app.router.add_post("/api/v5/trade/order", handle_place_order)
    app.router.add_post("/api/v5/trade/cancel-order", handle_cancel_order)
    app.router.add_get("/api/v5/trade/order", handle_query_order)

    # Mock-only control endpoints. / 仅 mock 控制端点。
    app.router.add_post("/_mock/faults", handle_set_faults)
    app.router.add_post("/_mock/orders/{ord_id}/fill", handle_inject_fill)
    app.router.add_post("/_mock/reset", handle_reset)

    return app, state


@contextlib.asynccontextmanager
async def run_mock_okx(
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    api_key: str = "mock-api-key",
    api_secret: str = "mock-api-secret",
    passphrase: str = "mock-passphrase",
    demo: bool = True,
) -> AsyncIterator[MockOkxServer]:
    """Start the mock and yield a :class:`MockOkxServer` until the block exits.

    启动 mock 并在 ``async with`` 块内 yield :class:`MockOkxServer`，退出时
    自动关闭。

    Port 0 means "let the OS pick"; the chosen port is exposed via
    ``MockOkxServer.base_url``. Pass an explicit port only when a test
    needs a known URL.

    端口 0 表示由操作系统分配；分配后的端口可从 ``base_url`` 取出。仅在测试
    必须使用固定 URL 时显式传入端口。
    """
    app, state = build_app(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        demo=demo,
    )
    runner = web.AppRunner(app, shutdown_timeout=0.1)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()

    # Resolve the actual chosen port. After ``site.start()`` aiohttp's
    # underlying asyncio Server is at ``site._server`` and its sockets
    # know the OS-assigned port. We avoid ``runner._servers`` because it
    # changed shape across aiohttp 3.x versions.
    #
    # site.start() 之后，aiohttp 内部的 asyncio Server 在 site._server，
    # 其 sockets 含有实际端口。不使用 runner._servers，因为该字段在
    # aiohttp 3.x 不同子版本里形态有变。
    actual_port = port
    underlying = getattr(site, "_server", None)
    if underlying is not None and getattr(underlying, "sockets", None):
        actual_port = underlying.sockets[0].getsockname()[1]
    base_url = f"http://{host}:{actual_port}"

    mock = MockOkxServer(
        base_url=base_url,
        state=state,
        runner=runner,
        site=site,
    )
    try:
        yield mock
    finally:
        await mock.aclose()
