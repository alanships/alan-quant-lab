from asyncio import run

import pytest

from okx_perp_reliable.exceptions import NetworkError, RateLimitError
from okx_perp_reliable.http import OkxHttpClient


def test_build_signed_headers_includes_demo_header() -> None:
    client = OkxHttpClient(
        api_key="key",
        api_secret="testsecret",
        passphrase="pass",
        demo=True,
        timeout=1,
    )

    headers = client.build_signed_headers(
        method="GET",
        request_path="/api/v5/account/balance?ccy=BTC",
        body="",
        timestamp="2020-12-08T09:08:57.715Z",
    )

    assert headers["OK-ACCESS-KEY"] == "key"
    assert headers["OK-ACCESS-PASSPHRASE"] == "pass"
    assert headers["x-simulated-trading"] == "1"
    assert headers["OK-ACCESS-SIGN"] == "tIo2xfZqxiQFcz9betm1JatDBrl8kfcdIERDUPL6kR0="


def test_build_request_path_puts_get_params_in_path() -> None:
    client = OkxHttpClient(
        api_key="key",
        api_secret="secret",
        passphrase="pass",
        demo=False,
        timeout=1,
    )

    assert (
        client.build_request_path(
            "/api/v5/trade/order",
            {"instId": "BTC-USDT-SWAP", "clOrdId": "sdkABC123"},
        )
        == "/api/v5/trade/order?instId=BTC-USDT-SWAP&clOrdId=sdkABC123"
    )


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self, content_type=None):
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response

    async def close(self):
        return None


def test_request_maps_429_to_rate_limit_error() -> None:
    run(_test_request_maps_429_to_rate_limit_error())


async def _test_request_maps_429_to_rate_limit_error() -> None:
    session = FakeSession(FakeResponse(429, {"code": "50011"}))
    client = OkxHttpClient(
        api_key="key",
        api_secret="secret",
        passphrase="pass",
        demo=False,
        timeout=1,
        session=session,
    )

    with pytest.raises(RateLimitError):
        await client.request("GET", "/api/v5/account/balance")


def test_request_maps_5xx_to_network_error() -> None:
    run(_test_request_maps_5xx_to_network_error())


async def _test_request_maps_5xx_to_network_error() -> None:
    session = FakeSession(FakeResponse(503, {"code": "50001"}))
    client = OkxHttpClient(
        api_key="key",
        api_secret="secret",
        passphrase="pass",
        demo=False,
        timeout=1,
        session=session,
    )

    with pytest.raises(NetworkError):
        await client.request("GET", "/api/v5/account/balance")
