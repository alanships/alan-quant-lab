"""Auth verification matching OKX v5 conventions.

与 OKX v5 鉴权规则对齐的签名校验。

We re-implement the verification side of HMAC-SHA256 + Base64 signing
so the mock can exercise the SDK's signing module against an
independent implementation. If both ends agree, the SDK signing is
correct; bugs in the mock would surface as bugs in the SDK during
self-tests, which is exactly what we want.

我们以独立实现重写签名校验侧，让 mock 能与 SDK 的签名模块互相验证：
两端达成一致即表明 SDK 签名实现正确；mock 的实现 bug 会在自测中暴露，
这正是我们想要的。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import datetime, timezone

# Required OKX headers. / 必需的 OKX 请求头。
REQUIRED_HEADERS = (
    "OK-ACCESS-KEY",
    "OK-ACCESS-SIGN",
    "OK-ACCESS-TIMESTAMP",
    "OK-ACCESS-PASSPHRASE",
)


class AuthCheckResult:
    """Container for an auth verification outcome. / 鉴权校验结果容器。"""

    __slots__ = ("ok", "scode", "message")

    def __init__(self, ok: bool, scode: str = "0", message: str = "") -> None:
        self.ok = ok
        self.scode = scode
        self.message = message

    @classmethod
    def success(cls) -> AuthCheckResult:
        return cls(True)

    @classmethod
    def failure(cls, scode: str, message: str) -> AuthCheckResult:
        return cls(False, scode, message)


def verify_request(
    *,
    headers: dict[str, str],
    method: str,
    request_path: str,
    body: str,
    expected_api_key: str,
    expected_secret: str,
    expected_passphrase: str,
    expected_demo: bool,
    timestamp_window_seconds: float,
) -> AuthCheckResult:
    """Verify a single inbound request against expected credentials.

    校验一次入站请求与预期凭据是否匹配。

    Returns ``AuthCheckResult`` instead of raising so that the routes
    layer can decide the HTTP status code (50111/50112/50113/50114 each
    map to a different sCode but the HTTP status stays 200 per OKX
    convention).

    使用返回值而非异常，方便路由层根据 sCode（50111/50112/50113/50114）
    决定具体响应；按 OKX 惯例 HTTP 状态码均为 200。
    """
    # 1. presence of required headers
    for required in REQUIRED_HEADERS:
        if required not in headers:
            return AuthCheckResult.failure(
                "50111", f"Missing required header {required}"
            )

    # 2. API key match
    if headers["OK-ACCESS-KEY"] != expected_api_key:
        return AuthCheckResult.failure("50111", "Invalid OK-ACCESS-KEY")

    # 3. passphrase match
    if headers["OK-ACCESS-PASSPHRASE"] != expected_passphrase:
        return AuthCheckResult.failure("50114", "Invalid OK-ACCESS-PASSPHRASE")

    # 4. timestamp window
    timestamp = headers["OK-ACCESS-TIMESTAMP"]
    if timestamp_window_seconds > 0:
        drift = _parse_timestamp_drift_seconds(timestamp)
        if drift is None:
            return AuthCheckResult.failure(
                "50112", "Invalid OK-ACCESS-TIMESTAMP format"
            )
        if abs(drift) > timestamp_window_seconds:
            return AuthCheckResult.failure(
                "50112",
                f"Timestamp drift {drift:.3f}s exceeds window "
                f"{timestamp_window_seconds:.0f}s",
            )

    # 5. demo flag consistency
    is_demo_call = headers.get("x-simulated-trading") == "1"
    if is_demo_call != expected_demo:
        return AuthCheckResult.failure(
            "50111",
            "x-simulated-trading flag does not match expected mode",
        )

    # 6. signature
    expected_sig = _compute_signature(
        timestamp=timestamp,
        method=method,
        request_path=request_path,
        body=body,
        secret=expected_secret,
    )
    if not hmac.compare_digest(expected_sig, headers["OK-ACCESS-SIGN"]):
        return AuthCheckResult.failure("50113", "Invalid signature")

    return AuthCheckResult.success()


def _compute_signature(
    *,
    timestamp: str,
    method: str,
    request_path: str,
    body: str,
    secret: str,
) -> str:
    prehash = f"{timestamp}{method.upper()}{request_path}{body}"
    digest = hmac.new(
        secret.encode("utf-8"),
        prehash.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _parse_timestamp_drift_seconds(ts: str) -> float | None:
    """Return drift between ``ts`` and now (seconds). None if unparseable.

    返回 ``ts`` 与当前时刻的偏差（秒）；无法解析返回 None。
    """
    try:
        # OKX accepts ISO-8601 with millisecond precision and trailing Z.
        normalized = ts.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return time.time() - parsed.timestamp()
