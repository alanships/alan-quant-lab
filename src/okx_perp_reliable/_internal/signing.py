"""OKX signing helpers. / OKX 签名工具。"""

import base64
import hashlib
import hmac
from datetime import datetime, timezone


def generate_timestamp() -> str:
    """Generate UTC ISO-8601 timestamp with milliseconds. / 生成 UTC 毫秒时间戳。"""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def sign_request(
    *,
    timestamp: str,
    method: str,
    request_path: str,
    body: str,
    secret: str,
) -> str:
    """Sign an OKX REST request. / 对 OKX REST 请求签名。"""
    prehash = f"{timestamp}{method.upper()}{request_path}{body}"
    digest = hmac.new(
        secret.encode("utf-8"),
        prehash.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")
