from okx_perp_reliable._internal.signing import generate_timestamp, sign_request


def test_generate_timestamp_uses_utc_millisecond_format() -> None:
    timestamp = generate_timestamp()

    assert timestamp.endswith("Z")
    assert "+" not in timestamp
    assert len(timestamp) == len("2026-05-04T12:34:56.789Z")


def test_sign_get_request_with_query_path() -> None:
    assert (
        sign_request(
            timestamp="2020-12-08T09:08:57.715Z",
            method="GET",
            request_path="/api/v5/account/balance?ccy=BTC",
            body="",
            secret="testsecret",
        )
        == "tIo2xfZqxiQFcz9betm1JatDBrl8kfcdIERDUPL6kR0="
    )


def test_sign_post_request_with_exact_json_body() -> None:
    body = '{"instId":"BTC-USDT-SWAP","lever":"5","mgnMode":"isolated"}'

    assert (
        sign_request(
            timestamp="2020-12-08T09:08:57.715Z",
            method="POST",
            request_path="/api/v5/account/set-leverage",
            body=body,
            secret="testsecret",
        )
        == "OT/HK3F/LEiu905vmeay9YXjEQ9btgftZ72dib5VYZQ="
    )
