import socket

import pytest

from atlas.urls import (
    UrlPolicyError,
    is_host_allowed,
    normalize_domain,
    normalize_url,
    validate_fetch_target,
)


def test_normalize_url_removes_tracking_fragment_and_default_port() -> None:
    result = normalize_url(
        "HTTPS://Example.COM:443/a/../docs//?utm_source=newsletter&b=2&a=1#section"
    )

    assert result == "https://example.com/docs/?a=1&b=2"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:password@example.com/",
        "https:///missing-host",
        "https://example.com:99999/",
    ],
)
def test_normalize_url_rejects_unsafe_or_invalid_urls(url: str) -> None:
    with pytest.raises(UrlPolicyError):
        normalize_url(url)


def test_allowlist_matches_only_domain_boundaries() -> None:
    allowed = [("example.com", True), ("exact.test", False)]

    assert is_host_allowed("example.com", allowed)
    assert is_host_allowed("docs.example.com", allowed)
    assert is_host_allowed("exact.test", allowed)
    assert not is_host_allowed("sub.exact.test", allowed)
    assert not is_host_allowed("example.com.attacker.test", allowed)


def test_normalize_domain_accepts_url_input() -> None:
    assert normalize_domain("https://Docs.Example.com/") == "docs.example.com"


def test_validate_fetch_target_rejects_private_dns_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def private_answer(
        _host: str, _port: int, *, type: socket.SocketKind
    ) -> list[tuple[socket.AddressFamily, socket.SocketKind, int, str, tuple[str, int]]]:
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", private_answer)

    with pytest.raises(UrlPolicyError, match="Non-public destination"):
        validate_fetch_target("https://example.com", [("example.com", True)])


def test_validate_fetch_target_accepts_public_dns_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def public_answer(
        _host: str, _port: int, *, type: socket.SocketKind
    ) -> list[tuple[socket.AddressFamily, socket.SocketKind, int, str, tuple[str, int]]]:
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", public_answer)

    target = validate_fetch_target("https://example.com", [("example.com", True)])

    assert target.host == "example.com"
    assert target.addresses == ("93.184.216.34",)
