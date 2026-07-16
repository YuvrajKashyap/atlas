import uuid
from typing import Any
from urllib.parse import urlsplit

from opensearchpy import OpenSearch

from atlas.config import Settings
from atlas.models import Document


class DocumentIndex:
    schema_version = 1

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        parsed = urlsplit(settings.opensearch_url)
        self.physical_index = f"{settings.opensearch_index_prefix}-v{self.schema_version}"
        self.read_alias = f"{settings.opensearch_index_prefix}-read"
        self.write_alias = f"{settings.opensearch_index_prefix}-write"
        self.client = OpenSearch(
            hosts=[
                {
                    "host": parsed.hostname or "localhost",
                    "port": parsed.port or (443 if parsed.scheme == "https" else 9200),
                    "scheme": parsed.scheme or "http",
                }
            ],
            http_auth=(settings.opensearch_username, settings.opensearch_password),
            verify_certs=settings.opensearch_verify_certs,
            ssl_show_warn=False,
            timeout=10,
            max_retries=2,
            retry_on_timeout=True,
        )

    def ensure_index(self) -> None:
        if self.client.indices.exists(index=self.physical_index):
            return
        self.client.indices.create(
            index=self.physical_index,
            body={
                "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                "mappings": {
                    "dynamic": "strict",
                    "properties": {
                        "document_id": {"type": "keyword"},
                        "run_id": {"type": "keyword"},
                        "url": {"type": "keyword", "ignore_above": 4096},
                        "canonical_url": {"type": "keyword", "ignore_above": 4096},
                        "host": {"type": "keyword"},
                        "title": {"type": "text"},
                        "description": {"type": "text"},
                        "headings": {"type": "text"},
                        "main_text": {"type": "text"},
                        "language": {"type": "keyword"},
                        "content_hash": {"type": "keyword"},
                        "extraction_confidence": {"type": "float"},
                        "text_length": {"type": "integer"},
                        "extracted_at": {"type": "date"},
                    },
                },
                "aliases": {
                    self.read_alias: {},
                    self.write_alias: {"is_write_index": True},
                },
            },
        )

    def index_document(self, document: Document) -> str:
        self.ensure_index()
        self.client.index(
            index=self.write_alias,
            id=str(document.id),
            body={
                "document_id": str(document.id),
                "run_id": str(document.run_id),
                "url": document.url,
                "canonical_url": document.canonical_url,
                "host": document.host,
                "title": document.title,
                "description": document.description,
                "headings": document.headings,
                "main_text": document.main_text,
                "language": document.language,
                "content_hash": document.content_hash,
                "extraction_confidence": document.extraction_confidence,
                "text_length": document.text_length,
                "extracted_at": document.extracted_at.isoformat(),
            },
            params={"refresh": "wait_for"},
        )
        return self.physical_index

    def search(
        self,
        query: str,
        *,
        run_id: uuid.UUID | None = None,
        host: str | None = None,
        min_confidence: float | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        filters: list[dict[str, Any]] = []
        if run_id is not None:
            filters.append({"term": {"run_id": str(run_id)}})
        if host:
            filters.append({"term": {"host": host}})
        if min_confidence is not None:
            filters.append({"range": {"extraction_confidence": {"gte": min_confidence}}})
        response = self.client.search(
            index=self.read_alias,
            body={
                "from": (page - 1) * page_size,
                "size": page_size,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": [
                                        "title^4",
                                        "headings^2",
                                        "description^1.5",
                                        "main_text",
                                    ],
                                    "type": "best_fields",
                                }
                            }
                        ],
                        "filter": filters,
                    }
                },
                "highlight": {
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                    "fields": {"title": {}, "description": {}, "main_text": {"fragment_size": 180}},
                },
            },
        )
        hits = response["hits"]
        total = hits["total"]["value"] if isinstance(hits["total"], dict) else hits["total"]
        return {
            "total": total,
            "took_ms": response.get("took", 0),
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    **hit["_source"],
                    "score": hit.get("_score"),
                    "highlights": hit.get("highlight", {}),
                }
                for hit in hits["hits"]
            ],
        }

    def health(self) -> dict[str, Any]:
        return self.client.cluster.health()
