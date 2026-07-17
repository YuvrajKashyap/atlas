import asyncio
import socket
import threading
import time
from collections.abc import Generator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from atlas.fetcher import (
    FetchTimeoutError,
    PinnedResolver,
    RedirectPolicyError,
    ResponseTooLargeError,
    fetch_url,
    is_html_content_type,
)
from atlas.models import CrawlRun


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        _ = (format, args)

    def do_GET(self) -> None:
        if self.path == "/redirect":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/ok")
            self.end_headers()
            return
        if self.path == "/no-location":
            self.send_response(HTTPStatus.FOUND)
            self.end_headers()
            return
        if self.path == "/large":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", "10000")
            self.end_headers()
            return
        if self.path == "/stream-large":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"x" * 10000)
            return
        if self.path == "/slow":
            time.sleep(0.2)
        body = b"<html><body>ok</body></html>"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("ETag", '"ok"')
        self.send_header("X-Secret", "must-not-be-copied")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def http_server() -> Generator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_port)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _run(port: int, *, timeout: float = 1, redirects: int = 2) -> CrawlRun:
    return CrawlRun(
        name="fetcher",
        user_agent="AtlasBot/test",
        request_timeout_seconds=timeout,
        max_response_bytes=1000,
        max_redirects=redirects,
        global_concurrency=2,
        per_domain_concurrency=1,
        allowed_ports=[port],
    )


def test_fetcher_pins_dns_follows_redirect_and_filters_headers(http_server: int) -> None:
    result = fetch_url(
        _run(http_server),
        f"http://localhost:{http_server}/redirect",
        [("localhost", False)],
        allow_private_networks=True,
        conditional_headers={"If-None-Match": '"old"'},
    )

    assert result.status_code == 200
    assert result.final_url.endswith("/ok")
    assert len(result.redirect_chain) == 1
    assert result.headers["etag"] == '"ok"'
    assert "x-secret" not in result.headers
    assert result.request_headers["If-None-Match"] == '"old"'


@pytest.mark.parametrize("path", ["/large", "/stream-large"])
def test_fetcher_enforces_declared_and_streamed_limits(http_server: int, path: str) -> None:
    with pytest.raises(ResponseTooLargeError):
        fetch_url(
            _run(http_server),
            f"http://localhost:{http_server}{path}",
            [("localhost", False)],
            allow_private_networks=True,
        )


def test_fetcher_rejects_bad_or_excess_redirects(http_server: int) -> None:
    with pytest.raises(RedirectPolicyError, match="Location"):
        fetch_url(
            _run(http_server),
            f"http://localhost:{http_server}/no-location",
            [("localhost", False)],
            allow_private_networks=True,
        )
    with pytest.raises(RedirectPolicyError, match="limit"):
        fetch_url(
            _run(http_server, redirects=0),
            f"http://localhost:{http_server}/redirect",
            [("localhost", False)],
            allow_private_networks=True,
        )


def test_fetcher_maps_timeout_and_content_type(http_server: int) -> None:
    with pytest.raises(FetchTimeoutError):
        fetch_url(
            _run(http_server, timeout=0.05),
            f"http://localhost:{http_server}/slow",
            [("localhost", False)],
            allow_private_networks=True,
        )
    assert is_html_content_type("text/html; charset=utf-8")
    assert not is_html_content_type(None)
    assert not is_html_content_type("application/json")


def test_pinned_resolver_rejects_another_hostname() -> None:
    async def verify() -> None:
        resolver = PinnedResolver("example.com", ("93.184.216.34",))
        records = await resolver.resolve("example.com", 443, socket.AF_UNSPEC)
        assert records[0]["host"] == "93.184.216.34"
        with pytest.raises(OSError, match="unvalidated"):
            await resolver.resolve("attacker.test", 443)
        await resolver.close()

    asyncio.run(verify())
