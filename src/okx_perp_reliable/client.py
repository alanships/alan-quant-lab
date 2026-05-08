"""Public client. / 公开客户端。"""

from decimal import Decimal
from typing import Any

from okx_perp_reliable._internal.error_mapping import build_error, should_raise_error
from okx_perp_reliable.enums import OrderSide, OrderStatus, OrderType, ResultStatus
from okx_perp_reliable.exceptions import (
    ConfigurationError,
    NetworkError,
    ReliableSdkError,
)
from okx_perp_reliable.http import OkxHttpClient
from okx_perp_reliable.idempotency import (
    InMemoryStateStore,
    StateStore,
    generate_cl_ord_id,
    validate_cl_ord_id,
)
from okx_perp_reliable.models import OrderRequest, OrderResult
from okx_perp_reliable.reconciliation import OrderReconciler


class ReliablePerpClient:
    """Reliable OKX perpetual swap client. / OKX 永续合约可靠性客户端。

    The client owns idempotent placement and reconciliation orchestration.
    客户端负责幂等下单和 reconciliation 编排。
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        passphrase: str,
        demo: bool = True,
        timeout: float = 5.0,
        reconciliation_timeout: float = 30.0,
        reconciliation_max_attempts: int = 3,
        reconciliation_51603_grace_seconds: float = 0.0,
        base_url: str = "https://www.okx.com",
        http_client: Any | None = None,
        state_store: StateStore | None = None,
    ) -> None:
        if not api_key or not api_secret or not passphrase:
            raise ConfigurationError("api_key, api_secret and passphrase are required")
        if timeout <= 0:
            raise ConfigurationError("timeout must be positive")
        if reconciliation_timeout <= 0:
            raise ConfigurationError("reconciliation_timeout must be positive")
        if reconciliation_max_attempts <= 0:
            raise ConfigurationError("reconciliation_max_attempts must be positive")
        if reconciliation_51603_grace_seconds < 0:
            raise ConfigurationError("reconciliation_51603_grace_seconds must be >= 0")
        if reconciliation_51603_grace_seconds > reconciliation_timeout:
            raise ConfigurationError(
                "reconciliation_51603_grace_seconds must not exceed "
                "reconciliation_timeout"
            )

        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.demo = demo
        self.timeout = timeout
        self.reconciliation_timeout = reconciliation_timeout
        self.reconciliation_max_attempts = reconciliation_max_attempts
        self.reconciliation_51603_grace_seconds = reconciliation_51603_grace_seconds
        self.base_url = base_url
        self.http_client = http_client or OkxHttpClient(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            demo=demo,
            timeout=timeout,
            base_url=base_url,
        )
        self.state_store = state_store or InMemoryStateStore()
        self.reconciler = OrderReconciler(
            http_client=self.http_client,
            max_attempts=reconciliation_max_attempts,
            timeout=reconciliation_timeout,
            reconciliation_51603_grace_seconds=reconciliation_51603_grace_seconds,
        )

    async def place_order(
        self,
        *,
        inst_id: str,
        side: OrderSide,
        order_type: OrderType,
        size: Decimal,
        cl_ord_id: str | None = None,
        price: Decimal | None = None,
        pos_side: str | None = None,
        td_mode: str = "cross",
        reduce_only: bool = False,
    ) -> OrderResult:
        """Place an idempotent order. / 发起幂等下单。

        The method returns CONFIRMED, FAILED, or UNKNOWN instead of leaking
        ambiguous timeout states. 该方法返回 CONFIRMED、FAILED 或 UNKNOWN，
        不把超时后的不确定状态泄漏给调用方。
        """
        request = OrderRequest(
            inst_id=inst_id,
            side=side,
            order_type=order_type,
            size=size,
            cl_ord_id=cl_ord_id or generate_cl_ord_id(),
            price=price,
            pos_side=pos_side,
            td_mode=td_mode,
            reduce_only=reduce_only,
        )
        validate_cl_ord_id(request.cl_ord_id or "")
        payload = _order_request_to_okx_payload(request)
        await self.state_store.record_pending(request.cl_ord_id or "", payload)

        try:
            response = await self.http_client.request(
                "POST",
                "/api/v5/trade/order",
                json_body=payload,
            )
            result = await self._handle_place_order_response(response, request)
        except NetworkError:
            result = await self.reconciler.reconcile(
                inst_id=request.inst_id,
                cl_ord_id=request.cl_ord_id or "",
            )

        await self.state_store.update_status(request.cl_ord_id or "", result)
        return result

    async def close(self) -> None:
        """Close underlying resources. / 关闭底层资源。"""
        close = getattr(self.http_client, "close", None)
        if close is not None:
            await close()

    async def _handle_place_order_response(
        self,
        response: dict[str, Any],
        request: OrderRequest,
    ) -> OrderResult:
        data = response.get("data") or []
        order_data = data[0] if data else {}
        code = str(response.get("code", "0"))
        if code != "0":
            s_code = str(order_data.get("sCode") or code)
            s_msg = str(
                order_data.get("sMsg")
                or response.get("msg")
                or "OKX place order failed"
            )
            error = build_error(
                s_code,
                s_msg,
                raw_response=response,
            )
            if isinstance(error, NetworkError):
                return await self.reconciler.reconcile(
                    inst_id=request.inst_id,
                    cl_ord_id=request.cl_ord_id or "",
                )
            _raise_if_decision_requires(error)
            return OrderResult(
                status=ResultStatus.FAILED,
                cl_ord_id=request.cl_ord_id or "",
                inst_id=request.inst_id,
                raw_response=response,
                error=error,
            )

        s_code = str(order_data.get("sCode", "0"))
        if s_code == "0":
            return OrderResult(
                status=ResultStatus.CONFIRMED,
                order_status=OrderStatus.LIVE,
                order_id=order_data.get("ordId") or None,
                cl_ord_id=order_data.get("clOrdId") or request.cl_ord_id or "",
                inst_id=request.inst_id,
                raw_response=response,
            )

        error = build_error(
            s_code,
            str(order_data.get("sMsg") or "OKX place order rejected"),
            raw_response=response,
        )
        if isinstance(error, NetworkError):
            return await self.reconciler.reconcile(
                inst_id=request.inst_id,
                cl_ord_id=request.cl_ord_id or "",
            )
        _raise_if_decision_requires(error)
        return OrderResult(
            status=ResultStatus.FAILED,
            cl_ord_id=request.cl_ord_id or "",
            inst_id=request.inst_id,
            raw_response=response,
            error=error,
        )


def _raise_if_decision_requires(error: ReliableSdkError) -> None:
    """Raise mapped errors that the project routes outside OrderResult.

    抛出项目决策要求不放入 OrderResult 的映射错误。
    """
    # Auth-class raise-vs-wrap policy is recorded in .codex/DECISIONS.md.
    if should_raise_error(error):
        raise error


def _order_request_to_okx_payload(request: OrderRequest) -> dict[str, str]:
    payload = {
        "instId": request.inst_id,
        "tdMode": request.td_mode,
        "side": request.side.value,
        "ordType": request.order_type.value,
        "sz": str(request.size),
        "clOrdId": request.cl_ord_id or "",
    }
    if request.price is not None:
        payload["px"] = str(request.price)
    if request.pos_side is not None:
        payload["posSide"] = request.pos_side
    if request.reduce_only:
        payload["reduceOnly"] = "true"
    return payload
