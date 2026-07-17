import base64
import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from atlas.config import Settings
from atlas.enums import ChangeKind
from atlas.indexer import DocumentIndex
from atlas.models import Document


class FakeIndices:
    def __init__(self) -> None:
        self.existing: set[str] = set()
        self.created: list[tuple[str, dict[str, object]]] = []
        self.alias_updates: list[dict[str, object]] = []

    def exists(self, *, index: str) -> bool:
        return index in self.existing

    def create(self, *, index: str, body: dict[str, object]) -> None:
        self.existing.add(index)
        self.created.append((index, body))

    def get_mapping(self, *, index: str) -> dict[str, object]:
        return {index: {"mappings": {"properties": {"title": {"type": "text"}}}}}

    def exists_alias(self, *, name: str) -> bool:
        return name in {"atlas-documents-read", "atlas-documents-write"}

    def get_alias(self, *, name: str) -> dict[str, object]:
        return {"atlas-documents-v1": {"aliases": {name: {}}}}

    def update_aliases(self, *, body: dict[str, object]) -> None:
        self.alias_updates.append(body)


class FakeCluster:
    def health(self) -> dict[str, object]:
        return {"status": "green", "number_of_nodes": 1}


class FakeOpenSearch:
    def __init__(self) -> None:
        self.indices = FakeIndices()
        self.cluster = FakeCluster()
        self.indexed: list[dict[str, object]] = []
        self.search_body: dict[str, object] | None = None

    def index(self, **kwargs: object) -> None:
        self.indexed.append(kwargs)

    def search(self, *, index: str, body: dict[str, object]) -> dict[str, object]:
        self.search_body = body
        return {
            "took": 3,
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_source": {"document_id": "doc-1", "title": "Atlas"},
                        "_score": 2.5,
                        "highlight": {"title": ["<mark>Atlas</mark>"]},
                        "sort": [2.5, "2026-07-16T00:00:00Z", "doc-1"],
                    }
                ],
            },
            "aggregations": {
                "hosts": {"buckets": [{"key": "example.com", "doc_count": 1}]},
                "languages": {"buckets": []},
                "change_kinds": {"buckets": []},
            },
        }


def _document() -> Document:
    return Document(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        frontier_entry_id=uuid.uuid4(),
        fetch_attempt_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        version_number=2,
        is_current=True,
        change_kind=ChangeKind.MINOR,
        url="https://example.com/page",
        canonical_url="https://example.com/page",
        host="example.com",
        title="Atlas page",
        description="Indexed content",
        language="en",
        headings=["Atlas"],
        main_text="Indexed Atlas page content",
        text_length=26,
        content_hash="a" * 64,
        simhash="0000000000000001",
        simhash_bands=[1, 0, 0, 0],
        extraction_confidence=0.95,
        parser_name="trafilatura",
        parser_version="2",
        extraction_warnings=[],
        extracted_at=datetime(2026, 7, 16, tzinfo=UTC),
    )


def test_index_lifecycle_search_facets_and_alias_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeOpenSearch()

    def create_client(*_args: object, **_kwargs: object) -> FakeOpenSearch:
        return client

    monkeypatch.setattr("atlas.indexer.OpenSearch", create_client)
    index = DocumentIndex(Settings(opensearch_url="https://localhost:9200"))
    document = _document()

    index.ensure_index()
    index.ensure_index()
    assert len(client.indices.created) == 1
    assert index.index_document(document) == "atlas-documents-v2"
    assert client.indexed[0]["id"] == str(document.id)

    cursor = base64.urlsafe_b64encode(json.dumps([1, "cursor"]).encode()).decode()
    result = index.search(
        "atlas",
        run_id=document.run_id,
        host="example.com",
        min_confidence=0.5,
        language="en",
        change_kind="minor",
        extracted_after="2026-01-01T00:00:00Z",
        cursor=cursor,
        page_size=1,
    )
    assert result["total"] == 1
    assert result["next_cursor"] is not None
    assert cast(dict[str, Any], result["facets"])["hosts"] == [{"value": "example.com", "count": 1}]
    assert client.search_body is not None and client.search_body["search_after"] == [1, "cursor"]

    build_id = uuid.uuid4()
    build_index = index.create_build_index(build_id)
    assert build_index.endswith(build_id.hex[:8])
    assert index.create_build_index(build_id) == build_index
    index.activate_index(build_index)
    assert client.indices.alias_updates
    assert index.health()["status"] == "green"
