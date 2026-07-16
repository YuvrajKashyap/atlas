from atlas.extractor import extract_page

HTML = """
<!doctype html>
<html lang="en">
  <head>
    <title>Atlas Test Page</title>
    <meta name="description" content="A deterministic extraction fixture.">
    <link rel="canonical" href="/canonical">
  </head>
  <body>
    <nav>Navigation that should not dominate extraction</nav>
    <main>
      <h1>Atlas Test Page</h1>
      <h2>Extraction</h2>
      <p>This is the primary article body with enough content to exercise extraction.</p>
      <a href="/next?utm_source=test">Next page</a>
      <a href="mailto:team@example.com">Email</a>
    </main>
  </body>
</html>
"""


def test_extract_page_returns_metadata_text_and_normalized_links() -> None:
    page = extract_page(HTML, "https://example.com/start")

    assert page.title == "Atlas Test Page"
    assert page.description == "A deterministic extraction fixture."
    assert page.language == "en"
    assert page.canonical_url == "https://example.com/canonical"
    assert page.headings == ["Atlas Test Page", "Extraction"]
    assert page.links == ["https://example.com/next"]
    assert "primary article body" in page.main_text
    assert len(page.content_hash) == 64
    assert 0 < page.confidence <= 1


def test_extract_page_falls_back_for_sparse_markup() -> None:
    page = extract_page("<html><body><p>tiny</p></body></html>", "https://example.com/")

    assert page.main_text == "tiny"
    assert "very_short_extraction" in page.warnings
