"""Timeout/reconciliation result handling example. / 超时确认结果处理示例。"""

from okx_perp_reliable import ResultStatus, UnknownStateError


def handle_result(result) -> None:
    """Handle post-reconciliation result. / 处理 reconciliation 后结果。"""
    if result.status == ResultStatus.CONFIRMED:
        print(f"confirmed: ordId={result.order_id} state={result.order_status}")
    elif result.status == ResultStatus.FAILED:
        print(f"failed: {result.error}")
    elif isinstance(result.error, UnknownStateError):
        print(f"unknown after {result.reconciliation_attempts} attempts")
        print(f"manual intervention required: clOrdId={result.cl_ord_id}")
    else:
        print(f"manual intervention required: clOrdId={result.cl_ord_id}")
