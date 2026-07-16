import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from atlas.models import CrawlRun
from atlas.urls import UrlPolicyError, normalize_url, validate_fetch_target


class ResponseTooLargeError(RuntimeError):
    pass


class RedirectPolicyError(RuntimeError):
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


SAFE_RESPONSE_HEADERS = {
    "content-type",
    "content-length",
    "etag",
    "last-modified",
    "cache-control",
    "retry-after",
}


def fetch_url(
    run: CrawlRun,
    url: str,
    allowed_domains: list[tuple[str, bool]],
    *,
    allow_private_networks: bool,
) -> FetchResult:
    timeout = httpx.Timeout(
        connect=run.request_timeout_seconds,
        read=run.request_timeout_seconds,
        write=run.request_timeout_seconds,
        pool=run.request_timeout_seconds,
    )
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    current_url = normalize_url(url)
    redirects: list[dict[str, Any]] = []
    started = time.perf_counter()

    with httpx.Client(
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
        headers={
            "User-Agent": run.user_agent,
            "Accept": "text/html,application/xhtml+xml;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        },
    ) as client:
        for redirect_count in range(run.max_redirects + 1):
            target = validate_fetch_target(
                current_url,
                allowed_domains,
                allow_private_networks=allow_private_networks,
            )
            with client.stream("GET", target.url) as response:
                if response.is_redirect:
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
                    )
                    redirects.append(
                        {"status_code": response.status_code, "from": target.url, "to": redirected}
                    )
                    current_url = redirected
                    continue

                content_type = response.headers.get("content-type")
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > run.max_response_bytes:
                            raise ResponseTooLargeError(
                                "Response Content-Length exceeds the run limit"
                            )
                    except ValueError:
                        pass

                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > run.max_response_bytes:
                        raise ResponseTooLargeError("Response body exceeds the run limit")
                    chunks.append(chunk)

                elapsed_ms = (time.perf_counter() - started) * 1000
                headers = {
                    key.lower(): value
                    for key, value in response.headers.items()
                    if key.lower() in SAFE_RESPONSE_HEADERS
                }
                return FetchResult(
                    status_code=response.status_code,
                    final_url=str(response.url),
                    headers=headers,
                    body=b"".join(chunks),
                    content_type=content_type,
                    latency_ms=round(elapsed_ms, 2),
                    redirect_chain=redirects,
                )

    raise UrlPolicyError("Fetch ended without a response")


def is_html_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type in {"text/html", "application/xhtml+xml"}
