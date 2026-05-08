"""In-memory order state for the mock OKX server.

Mock OKX 服务器的内存订单状态。

The store is intentionally tiny: just enough to back the four endpoints
the SDK touches (place / cancel / query / public time). Threading is not
a concern because the mock runs in the test event loop.

刻意保持极简：仅支持 SDK 当前会调用的四个端点（下单 / 撤单 / 查单 /
公共时间）。无需考虑线程安全，因为 mock 与测试运行在同一事件循环。
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class MockOrder:
    """A single mock order row. / 单条 mock 订单记录。

    Field names mirror OKX's ``GET /api/v5/trade/order`` response so the
    routes layer can serialize directly.

    字段命名对齐 OKX ``GET /api/v5/trade/order`` 的响应，方便路由层直接序列化。
    """

    ord_id: str
    cl_ord_id: str
    inst_id: str
    side: str  # "buy" / "sell"
    sz: Decimal
    px: Decimal | None
    ord_type: str  # "market" / "limit"
    td_mode: str = "cross"
    pos_side: str | None = None
    reduce_only: bool = False
    state: str = "live"  # live / partially_filled / filled / canceled
    fill_sz: Decimal = Decimal("0")
    avg_px: Decimal | None = None
    c_time_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    u_time_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_okx_payload(self) -> dict[str, str]:
        """Serialize to the dict shape OKX returns. / 序列化为 OKX 响应的 dict 形态。"""
        return {
            "instType": "SWAP",
            "instId": self.inst_id,
            "ordId": self.ord_id,
            "clOrdId": self.cl_ord_id,
            "tag": "",
            "px": "" if self.px is None else str(self.px),
            "sz": str(self.sz),
            "ordType": self.ord_type,
            "side": self.side,
            "posSide": self.pos_side or "net",
            "tdMode": self.td_mode,
            "accFillSz": str(self.fill_sz),
            "fillSz": str(self.fill_sz),
            "avgPx": "" if self.avg_px is None else str(self.avg_px),
            "state": self.state,
            "lever": "1",
            "fee": "0",
            "feeCcy": "USDT",
            "rebate": "0",
            "rebateCcy": "USDT",
            "category": "normal",
            "reduceOnly": str(self.reduce_only).lower(),
            "cTime": str(self.c_time_ms),
            "uTime": str(self.u_time_ms),
        }


class OrderStore:
    """In-memory order book keyed by ordId, with clOrdId index.

    内存订单簿，主键为 ordId，并维护 clOrdId 索引。
    """

    _ord_id_counter = itertools.count(1_700_000_000_000)

    def __init__(self) -> None:
        self._by_ord_id: dict[str, MockOrder] = {}
        self._by_cl_ord_id: dict[tuple[str, str], MockOrder] = {}

    # ------------------------------------------------------------------
    # mutation / 写入
    # ------------------------------------------------------------------

    def add(self, order: MockOrder) -> MockOrder:
        """Insert a new order. Raises if (instId, clOrdId) already exists.

        新增订单。若 (instId, clOrdId) 已存在则抛错，模拟 OKX 的去重行为。
        """
        key = (order.inst_id, order.cl_ord_id)
        if key in self._by_cl_ord_id:
            raise ValueError(f"duplicate clOrdId for instId: {key}")
        self._by_ord_id[order.ord_id] = order
        self._by_cl_ord_id[key] = order
        return order

    def cancel(self, ord_id: str) -> MockOrder | None:
        """Cancel an order if found and resting. / 撤单（若订单存在且仍是挂单态）。"""
        order = self._by_ord_id.get(ord_id)
        if order is None or order.state in {"filled", "canceled"}:
            return None
        order.state = "canceled"
        order.u_time_ms = int(time.time() * 1000)
        return order

    def fill(self, ord_id: str, fill_sz: Decimal, fill_px: Decimal) -> MockOrder | None:
        """Inject a fill (used by tests, not by routes).

        模拟成交（仅供测试代码使用，不暴露到 HTTP 路由层）。
        """
        order = self._by_ord_id.get(ord_id)
        if order is None:
            return None
        order.fill_sz += fill_sz
        order.avg_px = fill_px
        order.u_time_ms = int(time.time() * 1000)
        order.state = "filled" if order.fill_sz >= order.sz else "partially_filled"
        return order

    # ------------------------------------------------------------------
    # lookup / 查询
    # ------------------------------------------------------------------

    def get_by_ord_id(self, ord_id: str) -> MockOrder | None:
        return self._by_ord_id.get(ord_id)

    def get_by_cl_ord_id(self, inst_id: str, cl_ord_id: str) -> MockOrder | None:
        return self._by_cl_ord_id.get((inst_id, cl_ord_id))

    def all_orders(self) -> list[MockOrder]:
        return list(self._by_ord_id.values())

    # ------------------------------------------------------------------
    # housekeeping / 工具
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all state. / 清空全部状态。"""
        self._by_ord_id.clear()
        self._by_cl_ord_id.clear()

    @classmethod
    def next_ord_id(cls) -> str:
        """Generate a monotonically increasing fake ordId.

        生成单调递增的 mock ordId。
        """
        return str(next(cls._ord_id_counter))
