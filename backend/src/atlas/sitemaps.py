import gzip
import io
import time
from collections import deque
from dataclasses import dataclass

from defusedxml import ElementTree

from atlas.config import Settings
from atlas.fetcher import fetch_url
from atlas.models import CrawlRun
from atlas.urls import UrlPolicyError, host_for_url, is_host_allowed, normalize_url

MAX_SITEMAP_DOCUMENTS = 20
MAX_SITEMAP_URLS = 50_000
MAX_SITEMAP_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SitemapDiscovery:
    urls: tuple[str, ...]
    documents_fetched: int
    rejected_urls: int


def decode_sitemap_document(body: bytes) -> bytes:
    if body.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as archive:
            expanded = archive.read(MAX_SITEMAP_BYTES + 1)
        if len(expanded) > MAX_SITEMAP_BYTES:
            raise ValueError("Decompressed sitemap exceeds the size limit")
        return expanded
    return body


def parse_sitemap_document(body: bytes) -> tuple[str, list[str]]:
    root = ElementTree.fromstring(decode_sitemap_document(body))
    root_name = root.tag.rsplit("}", 1)[-1].lower()
    locations = [
        (element.text or "").strip()
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].lower() == "loc" and (element.text or "").strip()
    ]
    if root_name not in {"urlset", "sitemapindex"}:
        raise ValueError(f"Unsupported sitemap root element: {root_name}")
    return root_name, locations


def discover_sitemaps(
    run: CrawlRun,
    advertised_urls: tuple[str, ...],
    allowed_domains: list[tuple[str, bool]],
    settings: Settings,
    delay_ms: int | None = None,
) -> SitemapDiscovery:
    """Fetch a bounded sitemap graph and return safe, normalized crawl targets."""
    queue = deque(advertised_urls[:MAX_SITEMAP_DOCUMENTS])
    visited_documents: set[str] = set()
    discovered: dict[str, None] = {}
    rejected = 0
    request_delay_seconds = max(250, delay_ms or run.per_domain_delay_ms or 1000) / 1000
    next_request_at = time.monotonic() + request_delay_seconds

    while queue and len(visited_documents) < MAX_SITEMAP_DOCUMENTS:
        raw_sitemap_url = queue.popleft()
        try:
            sitemap_url = normalize_url(raw_sitemap_url)
            if not is_host_allowed(host_for_url(sitemap_url), allowed_domains):
                rejected += 1
                continue
        except UrlPolicyError:
            rejected += 1
            continue
        if sitemap_url in visited_documents:
            continue
        visited_documents.add(sitemap_url)

        remaining_delay = next_request_at - time.monotonic()
        if remaining_delay > 0:
            time.sleep(remaining_delay)

        result = fetch_url(
            run,
            sitemap_url,
            allowed_domains,
            allow_private_networks=settings.allow_private_networks,
            accept="application/xml,text/xml,application/gzip,*/*;q=0.1",
            max_response_bytes=MAX_SITEMAP_BYTES,
        )
        next_request_at = time.monotonic() + request_delay_seconds
        if not 200 <= result.status_code < 300:
            continue
        root_name, locations = parse_sitemap_document(result.body)
        if root_name == "sitemapindex":
            for location in locations:
                if len(queue) + len(visited_documents) >= MAX_SITEMAP_DOCUMENTS:
                    break
                queue.append(location)
            continue

        for location in locations:
            if len(discovered) >= MAX_SITEMAP_URLS:
                break
            try:
                normalized = normalize_url(location)
                if not is_host_allowed(host_for_url(normalized), allowed_domains):
                    rejected += 1
                    continue
            except UrlPolicyError:
                rejected += 1
                continue
            discovered.setdefault(normalized, None)

    return SitemapDiscovery(
        urls=tuple(discovered),
        documents_fetched=len(visited_documents),
        rejected_urls=rejected,
    )
