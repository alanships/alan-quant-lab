"""Basic usage example. / 基础使用示例。"""

import asyncio
import os
from decimal import Decimal

from okx_perp_reliable import OrderSide, OrderType, ReliablePerpClient


async def main() -> None:
    inst_id = os.getenv("OKX_E2E_INST_ID", "BTC-USDT-SWAP")
    pos_side = os.getenv("OKX_E2E_POS_SIDE", "long")
    size = Decimal(os.getenv("OKX_E2E_SIZE", "1"))
    client = ReliablePerpClient(
        api_key=os.environ["OKX_API_KEY"],
        api_secret=os.environ["OKX_API_SECRET"],
        passphrase=os.environ["OKX_PASSPHRASE"],
        demo=True,
    )

    try:
        result = await client.place_order(
            inst_id=inst_id,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=size,
            td_mode="cross",
            pos_side=pos_side,
        )
        print(result.model_dump())
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
