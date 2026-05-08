"""Order reconciliation. / 订单状态确认逻辑。"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from okx_perp_reliable._internal.error_mapping import build_error
from okx_perp_reliable.enums import OrderStatus, ResultStatus
from okx_perp_reliable.exceptions import (
    NetworkError,
    OrderNotFoundError,
    UnknownStateError,
)
from okx_perp_reliable.models import OrderResult


class OrderReconciler:
    """Reconcile timed-out order placement by clOrdId.

    用 clOrdId 查单确认超时订单。
    """

    def __init__(
        self,
        *,
        http_client: Any,
        max_attempts: int = 3,
        timeout: float = 30.0,
        reconciliation_51603_grace_seconds: float = 0.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a reconciler.

        创建订单状态确认器。

        ``reconciliation_51603_grace_seconds`` implements the opt-in 51603
        retry policy recorded in ``.codex/DECISIONS.md``. The default ``0.0``
        preserves immediate FAILED behavior.
        ``reconciliation_51603_grace_seconds`` 对应 ``.codex/DECISIONS.md``
        记录的 51603 可选重试策略。默认 ``0.0`` 保持立即 FAILED 行为。
        """
        self.http_client = http_client
        self.max_attempts = max_attempts
        self.timeout = timeout
        self.reconciliation_51603_grace_seconds = reconciliation_51603_grace_seconds
        self.sleep = sleep
        self.monotonic = monotonic

    async def reconcile(self, *, inst_id: str, cl_ord_id: str) -> OrderResult:
        """Reconcile an ambiguous order result. / 确认结果不明的订单。"""
        attempts = 0
        deadline = self.monotonic() + self.timeout
        not_found_deadline: float | None = None
        last_not_found: tuple[OrderNotFoundError, dict[str, Any] | None] | None = None
        backoff = [1.0, 2.0, 4.0]

        while attempts < self.max_attempts and self.monotonic() < deadline:
            await self.sleep(backoff[min(attempts, len(backoff) - 1)])
            attempts += 1
            try:
                payload = await self.http_client.request(
                    "GET",
                    "/api/v5/trade/order",
                    params={"instId": inst_id, "clOrdId": cl_ord_id},
                )
                code = str(payload.get("code", "0"))
                if code != "0":
                    error = build_error(
                        code,
                        str(payload.get("msg") or "OKX query order failed"),
                        raw_response=payload,
                    )
                    if isinstance(error, OrderNotFoundError):
                        if self.reconciliation_51603_grace_seconds <= 0:
                            return _failed_not_found_result(
                                inst_id=inst_id,
                                cl_ord_id=cl_ord_id,
                                attempts=attempts,
                                error=error,
                                raw_response=payload,
                            )
                        last_not_found = (error, payload)
                        if not_found_deadline is None:
                            not_found_deadline = (
                                self.monotonic()
                                + self.reconciliation_51603_grace_seconds
                            )
                        if self.monotonic() >= not_found_deadline:
                            return _failed_not_found_result(
                                inst_id=inst_id,
                                cl_ord_id=cl_ord_id,
                                attempts=attempts,
                                error=error,
                                raw_response=payload,
                            )
                    else:
                        raise error

                data = payload.get("data") or []
                if data:
                    return order_result_from_okx_order(
                        data[0],
                        fallback_inst_id=inst_id,
                        fallback_cl_ord_id=cl_ord_id,
                        raw_response=payload,
                        reconciliation_attempts=attempts,
                    )
            except OrderNotFoundError as exc:
                return _failed_not_found_result(
                    inst_id=inst_id,
                    cl_ord_id=cl_ord_id,
                    attempts=attempts,
                    error=exc,
                    raw_response=None,
                )
            except NetworkError:
                continue

        if last_not_found is not None:
            error, raw_response = last_not_found
            return _failed_not_found_result(
                inst_id=inst_id,
                cl_ord_id=cl_ord_id,
                attempts=attempts,
                error=error,
                raw_response=raw_response,
            )

        return OrderResult(
            status=ResultStatus.UNKNOWN,
            cl_ord_id=cl_ord_id,
            inst_id=inst_id,
            reconciliation_attempts=attempts,
            error=UnknownStateError(
                "Order state cannot be confirmed after reconciliation"
            ),
        )


def order_result_from_okx_order(
    order: dict[str, Any],
    *,
    fallback_inst_id: str,
    fallback_cl_ord_id: str,
    raw_response: dict[str, Any] | None,
    reconciliation_attempts: int,
) -> OrderResult:
    """Build result from OKX order detail. / 从 OKX 查单结果构造返回值。"""
    state = order.get("state")
    order_status = OrderStatus(state) if state in set(OrderStatus) else None
    return OrderResult(
        status=ResultStatus.CONFIRMED,
        order_status=order_status,
        order_id=order.get("ordId") or None,
        cl_ord_id=order.get("clOrdId") or fallback_cl_ord_id,
        inst_id=order.get("instId") or fallback_inst_id,
        filled_size=_decimal_or_none(order.get("accFillSz") or order.get("fillSz")),
        avg_price=_decimal_or_none(order.get("avgPx")),
        raw_response=raw_response,
        reconciliation_attempts=reconciliation_attempts,
    )


def _failed_not_found_result(
    *,
    inst_id: str,
    cl_ord_id: str,
    attempts: int,
    error: OrderNotFoundError,
    raw_response: dict[str, Any] | None,
) -> OrderResult:
    """Build a failed result for OKX order-not-found responses.

    为 OKX 订单不存在响应构造 FAILED 结果。
    """
    return OrderResult(
        status=ResultStatus.FAILED,
        cl_ord_id=cl_ord_id,
        inst_id=inst_id,
        raw_response=raw_response,
        reconciliation_attempts=attempts,
        error=error,
    )


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))
