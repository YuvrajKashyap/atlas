from atlas.retry import is_transient_status, retry_delay


def test_transient_http_status_policy() -> None:
    assert is_transient_status(408)
    assert is_transient_status(429)
    assert is_transient_status(503)
    assert not is_transient_status(404)
    assert not is_transient_status(200)


def test_retry_delay_is_deterministic_capped_and_spread() -> None:
    first = retry_delay(1, "entry-a")
    repeated = retry_delay(1, "entry-a")
    another_entry = retry_delay(1, "entry-b")
    capped = retry_delay(20, "entry-a")

    assert first == repeated
    assert first.total_seconds() >= 5
    assert another_entry != first
    assert capped.total_seconds() <= 450
