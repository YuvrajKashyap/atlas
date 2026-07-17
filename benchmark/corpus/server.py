import hashlib
import json
import os
import time
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlsplit

PAGE_COUNT = 10_000
SITEMAP_SHARDS = 10
OVERSIZED_BYTES = 3_000_000
COUNTERS: Counter[str] = Counter()
COUNTER_LOCK = Lock()


def _page_body(page_id: int) -> bytes:
    if page_id > 0 and page_id % 100 == 0:
        return _page_body(page_id // 100)
    if page_id > 0 and page_id % 101 == 0:
        return _page_body(page_id // 101).replace(
            b"crawler recovery verification", b"crawler recovery verification revised"
        )
    content_id = page_id
    near_duplicate_suffix = ""
    next_ids = ((page_id + offset) % PAGE_COUNT for offset in (1, 7, 97))
    links = "".join(f'<a href="/page/{target}">page {target}</a>' for target in next_ids)
    malformed = "<div><p>intentionally unclosed" if page_id % 997 == 0 else ""
    return (
        "<!doctype html><html lang='en'><head>"
        f"<title>Atlas corpus page {page_id}</title>"
        f"<meta name='description' content='Deterministic corpus item {content_id}'>"
        f"<link rel='canonical' href='/page/{page_id}'>"
        "</head><body>"
        f"<main><h1>Corpus page {content_id}</h1><p>Known deterministic content {content_id}"
        f"{near_duplicate_suffix} for crawler recovery verification.</p>{links}{malformed}</main>"
        "</body></html>"
    ).encode()


class CorpusHandler(BaseHTTPRequestHandler):
    server_version = "AtlasCorpus/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _record(self, key: str) -> None:
        with COUNTER_LOCK:
            COUNTERS[key] += 1

    def _send(
        self,
        body: bytes,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str = "text/html; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlsplit(self.path).path
        self._record(path)
        host = self.headers.get("Host", "corpus").split(":", 1)[0]
        base = f"http://{host}"

        if path == "/robots.txt":
            body = f"User-agent: *\nDisallow: /private/\nCrawl-delay: 0.25\nSitemap: {base}/sitemap.xml\n"
            self._send(body.encode(), content_type="text/plain; charset=utf-8")
            return
        if path == "/sitemap.xml":
            entries = "".join(
                f"<sitemap><loc>{base}/sitemap-{shard}.xml</loc></sitemap>"
                for shard in range(SITEMAP_SHARDS)
            )
            self._send(
                f"<?xml version='1.0'?><sitemapindex>{entries}</sitemapindex>".encode(),
                content_type="application/xml",
            )
            return
        if path.startswith("/sitemap-") and path.endswith(".xml"):
            try:
                shard = int(path.removeprefix("/sitemap-").removesuffix(".xml"))
            except ValueError:
                self._send(b"not found", status=HTTPStatus.NOT_FOUND)
                return
            if not 0 <= shard < SITEMAP_SHARDS:
                self._send(b"not found", status=HTTPStatus.NOT_FOUND)
                return
            start = shard * (PAGE_COUNT // SITEMAP_SHARDS)
            entries = "".join(
                f"<url><loc>{base}/page/{page_id}</loc></url>"
                for page_id in range(start, start + PAGE_COUNT // SITEMAP_SHARDS)
            )
            if shard == SITEMAP_SHARDS - 1:
                entries += "".join(
                    f"<url><loc>{base}{route}</loc></url>"
                    for route in (
                        "/redirect/1",
                        "/flaky/1",
                        "/oversized",
                        "/non-html",
                        "/slow",
                        "/private/blocked",
                    )
                )
            self._send(
                f"<?xml version='1.0'?><urlset>{entries}</urlset>".encode(),
                content_type="application/xml",
            )
            return
        if path == "/manifest.json":
            manifest = {
                "corpusVersion": 1,
                "pageCount": PAGE_COUNT,
                "sitemapShards": SITEMAP_SHARDS,
                "crawlTargetCount": PAGE_COUNT + 6,
                "faultRoutes": [
                    "/redirect/1",
                    "/flaky/1",
                    "/oversized",
                    "/non-html",
                    "/slow",
                    "/private/blocked",
                ],
            }
            self._send(json.dumps(manifest, sort_keys=True).encode(), content_type="application/json")
            return
        if path == "/__control/stats":
            with COUNTER_LOCK:
                data = dict(sorted(COUNTERS.items()))
            self._send(json.dumps(data).encode(), content_type="application/json")
            return
        if path == "/__control/reset":
            with COUNTER_LOCK:
                COUNTERS.clear()
            self._send(b'{"reset":true}', content_type="application/json")
            return
        if path.startswith("/page/"):
            try:
                page_id = int(path.removeprefix("/page/"))
            except ValueError:
                self._send(b"not found", status=HTTPStatus.NOT_FOUND)
                return
            if not 0 <= page_id < PAGE_COUNT:
                self._send(b"not found", status=HTTPStatus.NOT_FOUND)
                return
            body = _page_body(page_id)
            etag = '"' + hashlib.sha256(body).hexdigest() + '"'
            if self.headers.get("If-None-Match") == etag:
                self._send(b"", status=HTTPStatus.NOT_MODIFIED, headers={"ETag": etag})
                return
            self._send(body, headers={"ETag": etag, "Last-Modified": "Wed, 01 Jul 2026 00:00:00 GMT"})
            return
        if path.startswith("/redirect/"):
            target = path.removeprefix("/redirect/") or "0"
            self._send(b"", status=HTTPStatus.FOUND, headers={"Location": f"/page/{target}"})
            return
        if path.startswith("/flaky/"):
            with COUNTER_LOCK:
                attempt = COUNTERS[path]
            if attempt <= 2:
                self._send(b"temporary failure", status=HTTPStatus.SERVICE_UNAVAILABLE)
            else:
                self._send(_page_body(int(path.removeprefix("/flaky/"))))
            return
        if path == "/oversized":
            self._send(b"x" * OVERSIZED_BYTES, content_type="text/plain")
            return
        if path == "/non-html":
            self._send(b'{"kind":"unsupported"}', content_type="application/json")
            return
        if path == "/slow":
            time.sleep(float(os.getenv("CORPUS_SLOW_SECONDS", "3")))
            self._send(_page_body(42))
            return
        if path.startswith("/private/"):
            self._send(b"robots must block this route")
            return
        if path == "/":
            self._send(b"<html><body><a href='/page/0'>Start corpus</a></body></html>")
            return
        self._send(b"not found", status=HTTPStatus.NOT_FOUND, content_type="text/plain")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "80"))
    ThreadingHTTPServer(("0.0.0.0", port), CorpusHandler).serve_forever()
