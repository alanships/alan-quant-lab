"""Signed OKX REST transport. / OKX 签名 REST 传输层。"""

import asyncio
import json
from typing import Any
from urllib.parse import urlencode

import aiohttp

from okx_perp_reliable._internal.signing import generate_timestamp, sign_request
from okx_perp_reliable.exceptions import NetworkError, RateLimitError, ReliableSdkError


class OkxHttpClient:
    """Signed OKX REST client. / OKX 签名 REST 客户端。"""

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        passphrase: str,
        demo: bool,
        timeout: float,
        base_url: str = "https://www.okx.com",
        session: aiohttp.ClientSession | None = None,
        trust_env: bool = True,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.demo = demo
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self._session = session
        self._owns_session = session is None
        self.trust_env = trust_env

    async def close(self) -> None:
        """Close the owned aiohttp session. / 关闭内部持有的 aiohttp session。"""
        if self._session is not None and self._owns_session:
            await self._session.close()

    def build_request_path(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Build OKX request path including query. / 构造含 query 的请求路径。"""
        if not params:
            return path
        query = urlencode(
            {key: value for key, value in params.items() if value is not None}
        )
        return f"{path}?{query}" if query else path

    def build_signed_headers(
        self,
        *,
        method: str,
        request_path: str,
        body: str,
        timestamp: str | None = None,
    ) -> dict[str, str]:
        """Build signed OKX headers. / 构造 OKX 签名请求头。"""
        timestamp = timestamp or generate_timestamp()
        headers = {
            "Content-Type": "application/json",
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign_request(
                timestamp=timestamp,
                method=method,
                request_path=request_path,
                body=body,
                secret=self.api_secret,
            ),
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
        }
        if self.demo:
            headers["x-simulated-trading"] = "1"
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send signed OKX REST request. / 发送 OKX 签名 REST 请求。"""
        method = method.upper()
        request_path = self.build_request_path(path, params)
        body = (
            json.dumps(json_body, separators=(",", ":"), ensure_ascii=False)
            if json_body is not None
            else ""
        )
        headers = self.build_signed_headers(
            method=method,
            request_path=request_path,
            body=body,
        )
        session = self._session
        if session is None:
            session = aiohttp.ClientSession(trust_env=self.trust_env)
            self._session = session

        try:
            async with session.request(
                method,
                f"{self.base_url}{request_path}",
                data=body if body else None,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                try:
                    payload = await response.json(content_type=None)
                except ValueError:
                    payload = {
                        "code": str(response.status),
                        "msg": await response.text(),
                    }
                if response.status == 429:
                    raise RateLimitError(
                        "OKX rate limit reached",
                        okx_code=str(payload.get("code") or "50011"),
                        raw_response=payload,
                    )
                if response.status >= 500:
                    raise NetworkError(
                        f"OKX server error HTTP {response.status}",
                        okx_code=str(payload.get("code") or response.status),
                        raw_response=payload,
                    )
                return payload
        except ReliableSdkError:
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            raise NetworkError(f"OKX request failed: {exc}") from exc
