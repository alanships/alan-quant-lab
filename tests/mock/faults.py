"""Fault injection knobs for the mock OKX server.

Mock OKX 服务器的故障注入开关。

Each switch maps to a real failure mode the SDK is expected to handle.
The names are deliberately verbose so that a test reading
``mock.faults.place_succeeds_internally_but_returns_5xx = True``
is self-documenting.

每个开关对应 SDK 应能容忍的真实故障模式。命名故意冗长，使测试代码本身
即文档（"先把订单写进 store，再返回 5xx 给客户端"）。

The full list is intentionally small (≈10 switches). When you find
yourself wanting to add an 11th one, ask first whether the existing
combination already covers it.

开关数量刻意保持精简（~10 个）。若想加第 11 个，先确认现有开关组合是否
已覆盖该场景。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FaultConfig:
    """All fault-injection knobs for the mock server.

    Mock 服务器的全部故障注入开关。
    """

    # ------------------------------------------------------------------
    # Network / transport layer / 网络与传输层
    # ------------------------------------------------------------------

    response_delay_ms: float = 0.0
    """Add a fixed delay before every response. 0 disables.

    每次响应前增加固定延迟（毫秒）。0 表示禁用。"""

    drop_response: bool = False
    """If True, the server reads the request, processes it, then sleeps
    forever. The client will hit its HTTP timeout. Useful to simulate a
    response-lost-in-transit scenario.

    若为 True，服务器收到请求并处理后永久 sleep，客户端会触发 HTTP 超时。
    用于模拟"响应在传输途中丢失"。"""

    # ------------------------------------------------------------------
    # HTTP layer / HTTP 层
    # ------------------------------------------------------------------

    inject_5xx: bool = False
    """Return HTTP 503 *without* mutating order state. Models a transient
    upstream failure that the SDK should treat as retryable network error.

    返回 HTTP 503 但 **不** 改变订单状态，模拟瞬时网关错误，SDK 应作为
    可重试网络错误处理。"""

    inject_429: bool = False
    """Return HTTP 429 with ``Retry-After: 1`` and OKX sCode 50011.

    返回 HTTP 429 + ``Retry-After: 1`` + OKX sCode 50011。"""

    # ------------------------------------------------------------------
    # The killer fault: place succeeds, response lost
    # 关键故障：下单已落地，但响应未送达
    # ------------------------------------------------------------------

    place_succeeds_internally_but_returns_5xx: bool = False
    """Place the order in the store, **then** return HTTP 503. This is
    the canonical scenario the SDK's reconciliation must handle: the
    client cannot tell whether the order was accepted, but a follow-up
    query *will* find it.

    先把订单写入 store， **然后** 返回 HTTP 503。这是 SDK reconciliation
    必须处理的经典场景：客户端无从判断订单是否被接受，但后续查单一定能
    找到它。"""

    place_drops_response: bool = False
    """Place the order in the store, then never respond (timeout).
    Combine with reconciliation to verify CONFIRMED outcome.

    先把订单写入 store，再永久 sleep，客户端超时。配合 reconciliation
    用于验证 CONFIRMED 输出。"""

    # ------------------------------------------------------------------
    # Race window: order placed but not yet indexed for query
    # 竞态窗口：订单已落地但查单接口暂时找不到
    # ------------------------------------------------------------------

    query_returns_51603_for_first_n: int = 0
    """Number of consecutive query-by-clOrdId responses that should
    return OKX sCode 51603 (Order does not exist) **even when the order
    actually exists**, before behaving normally. Models the indexing
    race window between place and query.

    在前 N 次"按 clOrdId 查单"中返回 OKX sCode 51603（订单不存在），
    即便订单实际已存在；之后恢复正常。模拟下单与查单之间的索引竞态。"""

    # ------------------------------------------------------------------
    # Authentication / 鉴权
    # ------------------------------------------------------------------

    enforce_signature: bool = True
    """When True, missing or wrong signature returns 50113. When False,
    auth is skipped (useful when testing pure transport behavior).

    True 时校验签名，缺失或错误返回 50113。False 时跳过鉴权（仅用于
    单纯传输层测试）。"""

    enforce_timestamp_window_seconds: float = 30.0
    """OKX rejects timestamps drifted >30s. When the configured window
    is positive, requests outside the window get sCode 50112.

    OKX 拒绝偏离 >30s 的时间戳。配置为正值时，超窗请求返回 sCode 50112。"""

    # ------------------------------------------------------------------
    # Application-layer rejection / 应用层拒单
    # ------------------------------------------------------------------

    place_rejects_with_scode: str | None = None
    """If set, place_order returns success-shaped envelope with the
    given sCode (e.g. ``"51008"`` for insufficient balance), and does
    **not** insert into the store. Useful to test error mapping.

    设置后，下单接口返回成功包络但带指定 sCode（例如 ``"51008"`` 余额不足），
    且 **不** 写入 store。用于测试错误码映射。"""

    # ------------------------------------------------------------------
    # One-shot semantics / 一次性触发语义
    # ------------------------------------------------------------------

    apply_once: bool = False
    """When True, after the first request that matches *any* enabled
    fault, all faults are reset to defaults. Lets a test express
    "first request fails, retry succeeds" naturally.

    True 时，任何已启用的故障被首次触发后，所有故障会重置为默认值。
    便于测试表达"首次失败、重试成功"。"""

    # ------------------------------------------------------------------
    # Helpers / 工具
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset to default ("no faults") state. / 重置为默认（无故障）状态。"""
        defaults = FaultConfig()
        for field_name in defaults.__dataclass_fields__:
            setattr(self, field_name, getattr(defaults, field_name))

    def any_enabled(self) -> bool:
        """True if at least one network/HTTP/app-layer fault is enabled.

        若至少有一项网络/HTTP/应用层故障开启则返回 True。

        Auth-window settings do not count, because they are configuration
        rather than fault injection per se.
        """
        return (
            self.response_delay_ms > 0
            or self.drop_response
            or self.inject_5xx
            or self.inject_429
            or self.place_succeeds_internally_but_returns_5xx
            or self.place_drops_response
            or self.query_returns_51603_for_first_n > 0
            or self.place_rejects_with_scode is not None
        )
