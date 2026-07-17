import gzip

import pytest
from defusedxml.common import EntitiesForbidden

from atlas.config import Settings
from atlas.fetcher import FetchResult
from atlas.models import CrawlRun
from atlas.sitemaps import (
    MAX_SITEMAP_BYTES,
    decode_sitemap_document,
    discover_sitemaps,
    parse_sitemap_document,
)


def _run() -> CrawlRun:
    return CrawlRun(
        name="sitemap-test",
        user_agent="AtlasBot/test",
        request_timeout_seconds=2,
        max_response_bytes=1_000_000,
        max_redirects=2,
        per_domain_delay_ms=250,
        global_concurrency=2,
        per_domain_concurrency=1,
        allowed_ports=[80, 443],
    )


def _response(url: str, body: bytes, status: int = 200) -> FetchResult:
    return FetchResult(
        status_code=status,
        final_url=url,
        headers={},
        body=body,
        content_type="application/xml",
        latency_ms=1,
        redirect_chain=[],
        request_headers={},
    )


def test_locations_parses_namespaced_urlset_and_gzip() -> None:
    xml = b"""<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <url><loc>https://example.com/a</loc></url><url><loc>https://example.com/b</loc></url>
    </urlset>"""

    root, locations = parse_sitemap_document(gzip.compress(xml))

    assert root == "urlset"
    assert locations == ["https://example.com/a", "https://example.com/b"]


def test_locations_rejects_xml_entities() -> None:
    xml = b"<!DOCTYPE x [<!ENTITY boom 'unsafe'>]><urlset><url><loc>&boom;</loc></url></urlset>"

    with pytest.raises(EntitiesForbidden):
        parse_sitemap_document(xml)


def test_decode_rejects_gzip_expansion_over_limit() -> None:
    compressed = gzip.compress(b"x" * (MAX_SITEMAP_BYTES + 1))

    with pytest.raises(ValueError, match="Decompressed sitemap"):
        decode_sitemap_document(compressed)


def test_discovery_follows_index_normalizes_deduplicates_and_rejects_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = {
        "https://example.com/sitemap.xml": b"""<sitemapindex>
          <sitemap><loc>https://example.com/one.xml</loc></sitemap>
          <sitemap><loc>https://example.com/two.xml</loc></sitemap>
        </sitemapindex>""",
        "https://example.com/one.xml": b"""<urlset>
          <url><loc>https://example.com/a?utm_source=test</loc></url>
          <url><loc>https://attacker.test/no</loc></url>
        </urlset>""",
        "https://example.com/two.xml": b"""<urlset>
          <url><loc>https://example.com/a</loc></url>
          <url><loc>https://docs.example.com/b</loc></url>
        </urlset>""",
    }

    def fake_fetch(
        _run: CrawlRun,
        url: str,
        _domains: list[tuple[str, bool]],
        **_kwargs: object,
    ) -> FetchResult:
        return _response(url, responses[url])

    monkeypatch.setattr("atlas.sitemaps.fetch_url", fake_fetch)

    result = discover_sitemaps(
        _run(),
        ("https://example.com/sitemap.xml",),
        [("example.com", True)],
        Settings(),
    )

    assert result.documents_fetched == 3
    assert result.urls == ("https://example.com/a", "https://docs.example.com/b")
    assert result.rejected_urls == 1


def test_discovery_skips_non_successful_sitemap(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(
        _run: CrawlRun,
        url: str,
        _domains: list[tuple[str, bool]],
        **_kwargs: object,
    ) -> FetchResult:
        return _response(url, b"", 503)

    monkeypatch.setattr("atlas.sitemaps.fetch_url", unavailable)

    result = discover_sitemaps(
        _run(), ("https://example.com/sitemap.xml",), [("example.com", False)], Settings()
    )

    assert result.urls == ()
    assert result.documents_fetched == 1
