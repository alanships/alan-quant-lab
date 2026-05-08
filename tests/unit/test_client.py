from asyncio import run
from decimal import Decimal

from okx_perp_reliable.client import ReliablePerpClient
from okx_perp_reliable.enums import OrderSide, OrderStatus, OrderType, ResultStatus
from okx_perp_reliable.exceptions import InsufficientFundsError, NetworkError


async def _no_sleep(_: float) -> None:
    return None


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def request(self, method, path, *, params=None, json_body=None):
        self.requests.append(
            {"method": method, "path": path, "params": params, "json_body": json_body}
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def close(self):
        return None


def make_client(http):
    client = ReliablePerpClient(
        api_key="key",
        api_secret="secret",
        passphrase="pass",
        http_client=http,
    )
    client.reconciler.sleep = _no_sleep
    return client


def test_client_passes_base_url_to_default_http_client() -> None:
    client = ReliablePerpClient(
        api_key="key",
        api_secret="secret",
        passphrase="pass",
        base_url="http://127.0.0.1:12345",
    )

    assert client.base_url == "http://127.0.0.1:12345"
    assert client.http_client.base_url == "http://127.0.0.1:12345"


def test_place_order_confirmed_on_successful_scode() -> None:
    run(_test_place_order_confirmed_on_successful_scode())


async def _test_place_order_confirmed_on_successful_scode() -> None:
    http = FakeHttp(
        [
            {
                "code": "0",
                "data": [{"sCode": "0", "ordId": "1", "clOrdId": "sdkABC123"}],
            }
        ]
    )
    client = make_client(http)

    result = await client.place_order(
        inst_id="BTC-USDT-SWAP",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal("0.01"),
        cl_ord_id="sdkABC123",
    )

    assert result.status == ResultStatus.CONFIRMED
    assert result.order_status == OrderStatus.LIVE
    assert http.requests[0]["json_body"]["clOrdId"] == "sdkABC123"


def test_place_order_business_failure_returns_failed() -> None:
    run(_test_place_order_business_failure_returns_failed())


async def _test_place_order_business_failure_returns_failed() -> None:
    http = FakeHttp(
        [
            {
                "code": "0",
                "data": [
                    {
                        "sCode": "51008",
                        "sMsg": "Insufficient balance",
                        "clOrdId": "sdkABC123",
                    }
                ],
            }
        ]
    )
    client = make_client(http)

    result = await client.place_order(
        inst_id="BTC-USDT-SWAP",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal("0.01"),
        cl_ord_id="sdkABC123",
    )

    assert result.status == ResultStatus.FAILED
    assert isinstance(result.error, InsufficientFundsError)


def test_place_order_top_level_failure_uses_child_scode() -> None:
    run(_test_place_order_top_level_failure_uses_child_scode())


async def _test_place_order_top_level_failure_uses_child_scode() -> None:
    http = FakeHttp(
        [
            {
                "code": "1",
                "msg": "All operations failed",
                "data": [
                    {
                        "sCode": "51008",
                        "sMsg": "Insufficient balance",
                        "clOrdId": "sdkABC123",
                    }
                ],
            }
        ]
    )
    client = make_client(http)

    result = await client.place_order(
        inst_id="BTC-USDT-SWAP",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal("0.01"),
        cl_ord_id="sdkABC123",
    )

    assert result.status == ResultStatus.FAILED
    assert isinstance(result.error, InsufficientFundsError)
    assert result.error.okx_code == "51008"


def test_place_order_timeout_reconciles_by_cl_ord_id() -> None:
    run(_test_place_order_timeout_reconciles_by_cl_ord_id())


async def _test_place_order_timeout_reconciles_by_cl_ord_id() -> None:
    http = FakeHttp(
        [
            NetworkError("timeout"),
            {
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "clOrdId": "sdkABC123",
                        "ordId": "1",
                        "state": "filled",
                    }
                ],
            },
        ]
    )
    client = make_client(http)

    result = await client.place_order(
        inst_id="BTC-USDT-SWAP",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal("0.01"),
        cl_ord_id="sdkABC123",
    )

    assert result.status == ResultStatus.CONFIRMED
    assert http.requests[1]["method"] == "GET"
    assert http.requests[1]["params"] == {
        "instId": "BTC-USDT-SWAP",
        "clOrdId": "sdkABC123",
    }
