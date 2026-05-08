"""Idempotency helpers and local state. / 幂等工具和本地状态。"""

import asyncio
import secrets
import string
import time
from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel

from okx_perp_reliable.models import OrderResult

_ALPHANUM = string.ascii_letters + string.digits
_CL_ORD_ID_PREFIX = "sdk"
_CL_ORD_ID_RANDOM_LENGTH = 26
_MAX_CL_ORD_ID_LENGTH = 32


class StoredOrder(BaseModel):
    """Stored local order state. / 本地记录的订单状态。"""

    cl_ord_id: str
    status: str
    request: dict
    created_at: float


class StateStore(Protocol):
    """Replaceable local state store interface. / 可替换的本地状态存储接口。"""

    async def record_pending(self, cl_ord_id: str, request: dict) -> None:
        """Record a pending order. / 记录待确认订单。"""

    async def update_status(self, cl_ord_id: str, result: OrderResult) -> None:
        """Update an order after final result. / 根据最终结果更新订单。"""

    async def get(self, cl_ord_id: str) -> StoredOrder | None:
        """Fetch local order state. / 获取本地订单状态。"""

    async def list_pending(self, older_than: float) -> list[StoredOrder]:
        """List old pending orders. / 列出超过指定时间的待确认订单。"""


class InMemoryStateStore:
    """In-memory StateStore implementation. / 内存版状态存储。"""

    def __init__(self) -> None:
        self._orders: dict[str, StoredOrder] = {}
        self._lock = asyncio.Lock()

    async def record_pending(self, cl_ord_id: str, request: Mapping) -> None:
        """Record a pending order. / 记录待确认订单。"""
        async with self._lock:
            self._orders[cl_ord_id] = StoredOrder(
                cl_ord_id=cl_ord_id,
                status="PENDING",
                request=dict(request),
                created_at=time.time(),
            )

    async def update_status(self, cl_ord_id: str, result: OrderResult) -> None:
        """Update an order after final result. / 根据最终结果更新订单。"""
        async with self._lock:
            previous = self._orders.get(cl_ord_id)
            request = previous.request if previous else {}
            created_at = previous.created_at if previous else time.time()
            self._orders[cl_ord_id] = StoredOrder(
                cl_ord_id=cl_ord_id,
                status=result.status.value,
                request=request,
                created_at=created_at,
            )

    async def get(self, cl_ord_id: str) -> StoredOrder | None:
        """Fetch local order state. / 获取本地订单状态。"""
        async with self._lock:
            return self._orders.get(cl_ord_id)

    async def list_pending(self, older_than: float) -> list[StoredOrder]:
        """List old pending orders. / 列出超过指定时间的待确认订单。"""
        cutoff = time.time() - older_than
        async with self._lock:
            return [
                order
                for order in self._orders.values()
                if order.status == "PENDING" and order.created_at <= cutoff
            ]


def generate_cl_ord_id() -> str:
    """Generate an OKX-compatible client order ID. / 生成 OKX 兼容的 clOrdId。"""
    random_part = "".join(
        secrets.choice(_ALPHANUM) for _ in range(_CL_ORD_ID_RANDOM_LENGTH)
    )
    return f"{_CL_ORD_ID_PREFIX}{random_part}"


def validate_cl_ord_id(cl_ord_id: str) -> None:
    """Validate OKX client order ID constraints. / 校验 OKX clOrdId 规则。"""
    if not cl_ord_id:
        raise ValueError("clOrdId cannot be empty")
    if len(cl_ord_id) > _MAX_CL_ORD_ID_LENGTH:
        raise ValueError("clOrdId must be 32 characters or fewer")
    if not cl_ord_id[0].isalpha():
        raise ValueError("clOrdId must start with a letter")
    if not cl_ord_id.isalnum():
        raise ValueError("clOrdId must contain only letters and digits")
