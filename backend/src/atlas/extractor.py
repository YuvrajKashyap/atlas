import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import trafilatura
from selectolax.parser import HTMLParser

from atlas.urls import UrlPolicyError, normalize_url


@dataclass(slots=True)
class ExtractedPage:
    title: str | None
    description: str | None
    language: str | None
    headings: list[str]
    main_text: str
    canonical_url: str
    links: list[str]
    content_hash: str
    confidence: float
    warnings: list[str]
    parser_name: str = "trafilatura+selectolax"
    parser_version: str = trafilatura.__version__


def _meta_content(tree: HTMLParser, selector: str) -> str | None:
    node = tree.css_first(selector)
    if node is None:
        return None
    content = node.attributes.get("content")
    return content.strip() if content else None


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def extract_page(html: str, url: str) -> ExtractedPage:
    tree = HTMLParser(html)
    warnings: list[str] = []

    title_node = tree.css_first("title")
    title = _clean_text(title_node.text() if title_node else None)
    description = _meta_content(tree, 'meta[name="description"]') or _meta_content(
        tree, 'meta[property="og:description"]'
    )
    language = None
    html_node = tree.css_first("html")
    if html_node is not None:
        language = _clean_text(html_node.attributes.get("lang"))

    canonical_url = normalize_url(url)
    canonical_node = tree.css_first('link[rel="canonical"]')
    if canonical_node is not None and canonical_node.attributes.get("href"):
        try:
            canonical_url = normalize_url(urljoin(url, canonical_node.attributes["href"]))
        except UrlPolicyError:
            warnings.append("invalid_canonical_url")

    headings: list[str] = []
    for node in tree.css("h1, h2, h3"):
        text = _clean_text(node.text(separator=" "))
        if text and text not in headings:
            headings.append(text)
        if len(headings) >= 40:
            break

    links: list[str] = []
    seen_links: set[str] = set()
    for node in tree.css("a[href]"):
        href_value = node.attributes.get("href")
        href = href_value.strip() if href_value else ""
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "data:")):
            continue
        try:
            normalized = normalize_url(urljoin(url, href))
        except UrlPolicyError:
            continue
        if normalized not in seen_links:
            links.append(normalized)
            seen_links.add(normalized)

    extracted = trafilatura.bare_extraction(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    main_text = _clean_text(getattr(extracted, "text", None)) if extracted else None
    if extracted is not None:
        title = title or _clean_text(getattr(extracted, "title", None))
        description = description or _clean_text(getattr(extracted, "description", None))
        language = language or _clean_text(getattr(extracted, "language", None))

    if not main_text:
        warnings.append("trafilatura_empty_fallback_used")
        for selector in ("script", "style", "noscript", "svg", "nav", "footer"):
            for node in tree.css(selector):
                node.decompose()
        body = tree.css_first("body")
        main_text = _clean_text(body.text(separator=" ") if body else tree.text(separator=" "))

    if not main_text:
        main_text = ""
        warnings.append("empty_main_text")

    normalized_text = re.sub(r"\s+", " ", main_text).strip()
    content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

    confidence = 0.0
    confidence += min(len(normalized_text) / 2000, 0.55)
    confidence += 0.15 if title else 0.0
    confidence += 0.1 if description else 0.0
    confidence += 0.1 if headings else 0.0
    confidence += 0.1 if extracted is not None else 0.0
    if len(normalized_text) < 120:
        warnings.append("very_short_extraction")
    confidence = round(min(confidence, 1.0), 3)

    return ExtractedPage(
        title=title,
        description=description,
        language=language,
        headings=headings,
        main_text=normalized_text,
        canonical_url=canonical_url,
        links=links,
        content_hash=content_hash,
        confidence=confidence,
        warnings=warnings,
    )
