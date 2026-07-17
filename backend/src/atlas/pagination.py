import base64
import json
import uuid
from datetime import datetime
from typing import cast

from fastapi import HTTPException, status


def encode_cursor(timestamp: datetime, item_id: uuid.UUID) -> str:
    payload = json.dumps([timestamp.isoformat(), str(item_id)], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw_object = cast(object, json.loads(base64.urlsafe_b64decode(padded.encode()).decode()))
        if not isinstance(raw_object, list):
            raise ValueError("invalid cursor shape")
        raw = cast(list[object], raw_object)
        if len(raw) != 2:
            raise ValueError("invalid cursor shape")
        timestamp = datetime.fromisoformat(str(raw[0]))
        item_id = uuid.UUID(str(raw[1]))
        if timestamp.tzinfo is None:
            raise ValueError("cursor timestamp must include a timezone")
        return timestamp, item_id
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cursor is invalid or expired",
        ) from exc
