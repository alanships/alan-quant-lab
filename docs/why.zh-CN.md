# 为什么需要这个 SDK

## 1. 开场场景

凌晨两点，策略发出一笔 OKX 永续合约限价单。你的代码调用
`place_order()`，然后等了 30 秒，只拿到一个 `aiohttp` 超时。此时最难的
问题不是"代码报错了"，而是：这笔订单到底有没有到达 OKX？

你打开交易界面，暂时没看到这笔订单。你翻日志，只有一行超时异常，没有 OKX
订单号。如果直接重试，可能会多挂一笔同方向订单；如果直接当失败处理，可能错过
一笔已经被接受但暂时查不到的订单；如果让策略停住等人工介入，你的风险敞口仍在
变化。

这就是本 SDK 要处理的问题：不是预测市场，也不是替你做风控，而是把"下单结果
不明"从一团日志变成一个明确的程序契约。

## 2. 为什么技术上会发生

一次 REST 下单不是一个原子事件。客户端发出 HTTP 请求后，请求可能已经穿过网关，
甚至已经被后端系统处理，但响应在返回途中被网络中断。对 `aiohttp` 来说，这只
是一个 `TimeoutError`；对交易系统来说，订单可能已经存在。

HTTP 5xx 也不一定能说明订单失败。大型撮合系统通常有网关、风控、撮合、订单索引
等多个环节。网关返回 5xx 时，客户端只能知道"这次 HTTP 调用没有拿到可用响应"，
却不能仅凭这个状态码判断订单一定没有被接受。

OKX 的 `clOrdId` 机制正是解决这类问题的关键线索。OKX v5 文档在下单接口中提供
客户端自定义订单 ID `clOrdId`，并在查单接口中支持按 `clOrdId` 查询订单；文档
还说明如果同一个 `clOrdId` 关联多笔订单，查单只返回最新一笔。因此，稳妥做法是
始终生成唯一 `clOrdId`，并用它做事后确认。参考 OKX v5 API 文档：
<https://www.okx.com/docs-v5/en/>。

另一个通用的分布式系统问题：任何"先写入订单、再更新查询索引"的系统，都可能
出现一个短窗口——订单已经真实存在，但按 ID 查询时暂时返回 "not found"。这不是
某一家平台的特殊问题，而是大规模 place + query 系统常见的索引竞态窗口。

## 3. 这个 SDK 提供的契约

本 SDK 把 `place_order()` 的结果收敛成三个状态。

`CONFIRMED` 表示 OKX 已经确认订单。返回结果里会包含 `order_status`，用于区分
订单是挂单中、部分成交，还是已经成交。

`FAILED` 表示 SDK 已经拿到足够信息判断订单不会存在于 OKX。此时可以用新的
`clOrdId` 重新提交，而不是复用旧 ID。

`UNKNOWN` 表示 SDK 在限定次数和限定时间内仍无法确认。这个状态下不要自动重试；
应该人工检查账户、订单和日志。`UNKNOWN` 不是掩盖错误，而是承认系统边界。

兑现这个契约靠两件事。第一，每次调用都会带一个 SDK 生成或用户传入的唯一
`clOrdId`，并且在 HTTP 请求发出前先写入本地状态存储，相当于一次轻量的
write-ahead。第二，只要下单响应不明确——超时、5xx、响应丢失——SDK 就会按
`clOrdId` 查单并做有界重试。

查单返回 OKX sCode `51603`（订单不存在）时，默认会被收敛为确定的 `FAILED`。
如果你在自己环境里测量到存在短暂索引竞态，可以显式设置
`reconciliation_51603_grace_seconds`，让 SDK 在这个窗口内继续确认。这个参数是
选择项，不推荐固定值；它应该来自你自己的账户模式、网络条件和实测延迟。

## 4. 这个 SDK 不做什么

它不是多平台封装，只做 OKX USDT 本位永续合约。它不是仓位管理器、资金管理器或
风险系统。它不是策略框架，也不是回测框架。

它也不做 WebSocket。第一版只覆盖 REST 下单和按 `clOrdId` 查单确认。实时成交、
订单流、账户推送都不在当前契约内。

它不能阻止止损触发被平台内部流程延迟，不能阻止强平，不能阻止自动减仓。这些是
交易平台自身的行为，不是 SDK 能承诺的下单返回值。

它也不能替你扛住平台停机。如果 OKX 长时间维护或不可用，SDK 至多在有限重试后
返回 `UNKNOWN`，或抛出传输类错误。这不是设计缺陷，而是正确地告诉调用方：现在
没有足够信息继续自动行动。

这种克制很重要。一个可靠的 SDK 不应该把所有交易问题包装成"已经处理"，而应当
在自己能负责的范围内给出清楚答案，并明确说出范围之外的事不归它管。

## 5. 如何开始

下面的示例只配置 `demo=True`，不会碰正式交易环境。把凭证放进环境变量后再运行。

```python
# pip install okx-perp-reliable
import asyncio
import os
from decimal import Decimal

from okx_perp_reliable import (
    OrderSide,
    OrderType,
    ReliablePerpClient,
    ResultStatus,
)


async def main() -> None:
    client = ReliablePerpClient(
        api_key=os.environ["OKX_API_KEY"],
        api_secret=os.environ["OKX_API_SECRET"],
        passphrase=os.environ["OKX_PASSPHRASE"],
        demo=True,
    )
    try:
        result = await client.place_order(
            inst_id="BTC-USDT-SWAP",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("1"),
            price=Decimal("10000"),
            pos_side="long",
        )
    finally:
        await client.close()

    match result.status:
        case ResultStatus.CONFIRMED:
            print("confirmed", result.order_status)
        case ResultStatus.FAILED:
            print("failed", result.error)
        case ResultStatus.UNKNOWN:
            print("unknown; inspect manually")


if __name__ == "__main__":
    asyncio.run(main())
```
