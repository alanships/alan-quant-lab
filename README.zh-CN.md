# okx-perp-reliable

[![CI](https://github.com/alanships/alan-quant-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/alanships/alan-quant-lab/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/okx-perp-reliable.svg)](https://pypi.org/project/okx-perp-reliable/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

面向 OKX USDT 本位永续合约 REST 下单的可靠 asyncio SDK。

![Status Beta](https://img.shields.io/badge/status-beta-yellow)

## 为什么存在

当 OKX 已接受订单、但客户端在收到响应前超时时，`place_order()` 的结果会变得
不明确。本 SDK 使用幂等 `clOrdId` 和有界的按 `clOrdId` 查单确认流程，让调用方
收到三种明确结果之一：`CONFIRMED`、`FAILED` 或 `UNKNOWN`。完整背景见
[docs/why.md](docs/why.md)。

## 安装

```bash
pip install okx-perp-reliable
```

## 最小示例

```python
import asyncio
from decimal import Decimal

from okx_perp_reliable import (
    AuthenticationError,
    OrderSide,
    OrderType,
    ReliablePerpClient,
    ResultStatus,
)


async def main() -> None:
    client = ReliablePerpClient(
        api_key="...",
        api_secret="...",
        passphrase="...",
        demo=True,
    )
    try:
        try:
            result = await client.place_order(
                inst_id="BTC-USDT-SWAP",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                size=Decimal("0.01"),
                pos_side="long",
            )
        except AuthenticationError as e:
            # 配置类错误（签名、时间戳、passphrase）
            # 会抛出异常，不会包装进 OrderResult。
            print("auth failed:", e.okx_code, e)
            return

        match result.status:
            case ResultStatus.CONFIRMED:
                print("confirmed", result.order_status)
            case ResultStatus.FAILED:
                print("failed", result.error)
            case ResultStatus.UNKNOWN:
                print("unknown; inspect manually")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

## Mock 基础设施

集成测试使用的确定性进程内 OKX mock 记录在
[tests/mock/README.md](tests/mock/README.md)。它是测试基础设施，不属于发布的
SDK 包。

## 许可证和作者

MIT License。维护者：Alan。

English README: [README.md](README.md).
