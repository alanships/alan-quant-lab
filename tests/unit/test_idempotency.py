import re
from asyncio import run

import pytest

from okx_perp_reliable.enums import ResultStatus
from okx_perp_reliable.idempotency import (
    InMemoryStateStore,
    StoredOrder,
    generate_cl_ord_id,
    validate_cl_ord_id,
)
from okx_perp_reliable.models import OrderResult


def test_stored_order_skeleton() -> None:
    stored = StoredOrder(
        cl_ord_id="sdkABC123",
        status="PENDING",
        request={"instId": "BTC-USDT-SWAP"},
        created_at=1.0,
    )

    assert stored.cl_ord_id == "sdkABC123"


def test_generate_cl_ord_id_matches_okx_constraints() -> None:
    cl_ord_id = generate_cl_ord_id()

    assert len(cl_ord_id) == 29
    assert re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,31}", cl_ord_id)


@pytest.mark.parametrize("bad", ["", "1abc", "abc-123", "a" * 33])
def test_validate_cl_ord_id_rejects_invalid_values(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_cl_ord_id(bad)


def test_in_memory_state_store_records_and_updates() -> None:
    run(_test_in_memory_state_store_records_and_updates())


async def _test_in_memory_state_store_records_and_updates() -> None:
    store = InMemoryStateStore()

    await store.record_pending("sdkABC123", {"instId": "BTC-USDT-SWAP"})
    pending = await store.get("sdkABC123")
    assert pending is not None
    assert pending.status == "PENDING"
    assert await store.list_pending(older_than=0) == [pending]

    await store.update_status(
        "sdkABC123",
        OrderResult(
            status=ResultStatus.CONFIRMED,
            cl_ord_id="sdkABC123",
            inst_id="BTC-USDT-SWAP",
        ),
    )

    updated = await store.get("sdkABC123")
    assert updated is not None
    assert updated.status == "CONFIRMED"
