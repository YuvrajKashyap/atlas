import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from atlas.pagination import decode_cursor, encode_cursor


def test_cursor_round_trip() -> None:
    timestamp = datetime(2026, 7, 16, 12, 30, tzinfo=UTC)
    item_id = uuid.UUID("20d2e6a2-d72d-421c-b40d-a41db36be254")

    assert decode_cursor(encode_cursor(timestamp, item_id)) == (timestamp, item_id)


@pytest.mark.parametrize("cursor", ["not-base64", "W10", "WyIyMDI2LTAxLTAxIiwgImJhZCJd"])
def test_cursor_rejects_invalid_payload(cursor: str) -> None:
    with pytest.raises(HTTPException) as error:
        decode_cursor(cursor)

    assert error.value.status_code == 422
