def test_public_imports() -> None:
    import okx_perp_reliable as sdk

    assert sdk.ReliablePerpClient is not None
    assert sdk.OrderSide.BUY.value == "buy"
    assert sdk.OrderType.MARKET.value == "market"
    assert sdk.ResultStatus.CONFIRMED.value == "CONFIRMED"
