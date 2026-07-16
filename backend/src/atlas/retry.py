import hashlib
from datetime import timedelta

TRANSIENT_STATUS_CODES = {408, 425, 429}


def is_transient_status(status_code: int) -> bool:
    return status_code in TRANSIENT_STATUS_CODES or 500 <= status_code <= 599


def retry_delay(retry_number: int, stable_key: str, *, base_seconds: int = 5) -> timedelta:
    """Return capped exponential backoff with deterministic jitter.

    Deterministic jitter keeps tests repeatable while spreading jobs with different IDs.
    """
    exponent = max(0, retry_number - 1)
    base = min(base_seconds * (2**exponent), 300)
    digest = hashlib.sha256(f"{stable_key}:{retry_number}".encode()).digest()
    jitter = int.from_bytes(digest[:2]) % max(1, base // 2 + 1)
    return timedelta(seconds=base + jitter)
