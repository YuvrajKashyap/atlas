import asyncio
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult

from atlas.models import CrawlRun
from atlas.urls import UrlPolicyError, normalize_url, validate_fetch_target


class ResponseTooLargeError(RuntimeError):
    pass


class RedirectPolicyError(RuntimeError):
    pass


class FetchNetworkError(RuntimeError):
    pass


class FetchTimeoutError(RuntimeError):
    pass


@dataclass(slots=True)
class FetchResult:
    status_code: int
    final_url: str
    headers: dict[str, str]
    body: bytes
    content_type: str | None
    latency_ms: float
    redirect_chain: list[dict[str, Any]]
    request_headers: dict[str, str]


SAFE_RESPONSE_HEADERS = {
    "content-type",
    "content-length",
    "etag",
    "last-modified",
    "cache-control",
    "retry-after",
}


class PinnedResolver(AbstractResolver):
    """Resolve a validated hostname only to the addresses approved by URL policy."""

    def __init__(self, hostname: str, addresses: tuple[str, ...]) -> None:
        self.hostname = hostname
        self.addresses = addresses

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_UNSPEC
    ) -> list[ResolveResult]:
        if host.rstrip(".").lower() != self.hostname.rstrip(".").lower():
            raise OSError("Resolver received an unvalidated hostname")
        return [
            ResolveResult(
                hostname=host,
                host=address,
                port=port,
                family=socket.AF_INET6 if ":" in address else socket.AF_INET,
                proto=0,
                flags=0,
            )
            for address in self.addresses
        ]

    async def close(self) -> None:
        return None


async def _fetch_url_async(
    run: CrawlRun,
    url: str,
    allowed_domains: list[tuple[str, bool]],
    *,
    allow_private_networks: bool,
    conditional_headers: dict[str, str] | None,
    accept: str,
    max_response_bytes: int | None,
) -> FetchResult:
    current_url = normalize_url(url)
    redirects: list[dict[str, Any]] = []
    started = time.perf_counter()
    response_limit = max_response_bytes or run.max_response_bytes
    request_headers = {
        "User-Agent": run.user_agent,
        "Accept": accept,
        "Accept-Encoding": "gzip, deflate",
        **(conditional_headers or {}),
    }
    timeout = aiohttp.ClientTimeout(
        total=run.request_timeout_seconds,
        connect=run.request_timeout_seconds,
        sock_read=run.request_timeout_seconds,
    )

    try:
        for redirect_count in range(run.max_redirects + 1):
            target = validate_fetch_target(
                current_url,
                allowed_domains,
                allow_private_networks=allow_private_networks,
                allowed_ports=set(run.allowed_ports),
            )
            resolver = PinnedResolver(target.host, target.addresses)
            connector = aiohttp.TCPConnector(
                resolver=resolver,
                use_dns_cache=False,
                limit=max(1, run.global_concurrency),
                limit_per_host=max(1, run.per_domain_concurrency),
                ttl_dns_cache=0,
            )
            async with aiohttp.ClientSession(  # noqa: SIM117 - connector must close before redirect
                connector=connector,
                timeout=timeout,
                headers=request_headers,
                auto_decompress=True,
            ) as client:
                async with client.get(target.url, allow_redirects=False) as response:
                    if 300 <= response.status < 400:
                        location = response.headers.get("location")
                        if not location:
                            raise RedirectPolicyError(
                                "Redirect response did not include a Location header"
                            )
                        if redirect_count >= run.max_redirects:
                            raise RedirectPolicyError("Redirect limit exceeded")
                        redirected = normalize_url(urljoin(target.url, location))
                        validate_fetch_target(
                            redirected,
                            allowed_domains,
                            allow_private_networks=allow_private_networks,
                            allowed_ports=set(run.allowed_ports),
                        )
                        redirects.append(
                            {"status_code": response.status, "from": target.url, "to": redirected}
                        )
                        current_url = redirected
                        continue

                    content_type = response.headers.get("content-type")
                    content_length = response.headers.get("content-length")
                    if content_length is not None:
                        try:
                            if int(content_length) > response_limit:
                                raise ResponseTooLargeError(
                                    "Response Content-Length exceeds the run limit"
                                )
                        except ValueError:
                            pass

                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        size += len(chunk)
                        if size > response_limit:
                            raise ResponseTooLargeError("Response body exceeds the run limit")
                        chunks.append(chunk)

                    elapsed_ms = (time.perf_counter() - started) * 1000
                    headers = {
                        key.lower(): value
                        for key, value in response.headers.items()
                        if key.lower() in SAFE_RESPONSE_HEADERS
                    }
                    return FetchResult(
                        status_code=response.status,
                        final_url=str(response.url),
                        headers=headers,
                        body=b"".join(chunks),
                        content_type=content_type,
                        latency_ms=round(elapsed_ms, 2),
                        redirect_chain=redirects,
                        request_headers=request_headers,
                    )
    except TimeoutError as exc:
        raise FetchTimeoutError(str(exc)) from exc
    except aiohttp.ClientError as exc:
        raise FetchNetworkError(str(exc)) from exc

    raise UrlPolicyError("Fetch ended without a response")


def fetch_url(
    run: CrawlRun,
    url: str,
    allowed_domains: list[tuple[str, bool]],
    *,
    allow_private_networks: bool,
    conditional_headers: dict[str, str] | None = None,
    accept: str = "text/html,application/xhtml+xml;q=0.9",
    max_response_bytes: int | None = None,
) -> FetchResult:
    return asyncio.run(
        _fetch_url_async(
            run,
            url,
            allowed_domains,
            allow_private_networks=allow_private_networks,
            conditional_headers=conditional_headers,
            accept=accept,
            max_response_bytes=max_response_bytes,
        )
    )


def is_html_content_type(content_type: str | None, allowed: list[str] | None = None) -> bool:
    if content_type is None:
        return False
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type in set(allowed or ["text/html", "application/xhtml+xml"])
