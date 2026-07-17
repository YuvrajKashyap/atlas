import base64
import json
import uuid
from typing import Any, cast
from urllib.parse import urlsplit

import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

from atlas.config import Settings
from atlas.models import Document


class DocumentIndex:
    schema_version = 2

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        parsed = urlsplit(settings.opensearch_url)
        self.physical_index = f"{settings.opensearch_index_prefix}-v{self.schema_version}"
        self.read_alias = f"{settings.opensearch_index_prefix}-read"
        self.write_alias = f"{settings.opensearch_index_prefix}-write"
        http_auth: tuple[str, str] | AWSV4SignerAuth
        if settings.opensearch_aws_region:
            credentials = cast(Any, boto3.Session().get_credentials())
            if credentials is None:
                raise RuntimeError("AWS credentials are required for managed OpenSearch")
            http_auth = AWSV4SignerAuth(credentials, settings.opensearch_aws_region, "es")
        else:
            http_auth = (settings.opensearch_username, settings.opensearch_password)
        self.client = OpenSearch(
            hosts=[
                {
                    "host": parsed.hostname or "localhost",
                    "port": parsed.port or (443 if parsed.scheme == "https" else 9200),
                    "scheme": parsed.scheme or "http",
                }
            ],
            http_auth=http_auth,
            connection_class=RequestsHttpConnection,
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
                        "resource_id": {"type": "keyword"},
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
                        "simhash": {"type": "keyword"},
                        "version_number": {"type": "integer"},
                        "is_current": {"type": "boolean"},
                        "change_kind": {"type": "keyword"},
                        "duplicate_cluster_id": {"type": "keyword"},
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

    def index_document(self, document: Document, *, index_name: str | None = None) -> str:
        self.ensure_index()
        self.client.index(
            index=index_name or self.write_alias,
            id=str(document.id),
            body={
                "document_id": str(document.id),
                "resource_id": str(document.resource_id) if document.resource_id else None,
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
                "simhash": document.simhash,
                "version_number": document.version_number,
                "is_current": document.is_current,
                "change_kind": document.change_kind.value,
                "duplicate_cluster_id": (
                    str(document.duplicate_cluster_id) if document.duplicate_cluster_id else None
                ),
                "extraction_confidence": document.extraction_confidence,
                "text_length": document.text_length,
                "extracted_at": document.extracted_at.isoformat(),
            },
            params={"refresh": "wait_for"},
        )
        return index_name or self.physical_index

    def search(
        self,
        query: str,
        *,
        run_id: uuid.UUID | None = None,
        host: str | None = None,
        min_confidence: float | None = None,
        language: str | None = None,
        change_kind: str | None = None,
        current_only: bool = True,
        extracted_after: str | None = None,
        cursor: str | None = None,
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
        if language:
            filters.append({"term": {"language": language}})
        if change_kind:
            filters.append({"term": {"change_kind": change_kind}})
        if current_only:
            filters.append({"term": {"is_current": True}})
        if extracted_after:
            filters.append({"range": {"extracted_at": {"gte": extracted_after}}})
        search_after: list[object] | None = None
        if cursor:
            search_after = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        body: dict[str, Any] = {
            "size": page_size,
            "sort": [
                {"_score": "desc"},
                {"extracted_at": "desc"},
                {"document_id": "asc"},
            ],
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
            "aggs": {
                "hosts": {"terms": {"field": "host", "size": 20}},
                "languages": {"terms": {"field": "language", "size": 20}},
                "change_kinds": {"terms": {"field": "change_kind", "size": 10}},
            },
        }
        if search_after is not None:
            body["search_after"] = search_after
        elif page > 1:
            body["from"] = (page - 1) * page_size
        response = self.client.search(
            index=self.read_alias,
            body=body,
        )
        hits = response["hits"]
        total = hits["total"]["value"] if isinstance(hits["total"], dict) else hits["total"]
        result_hits = hits["hits"]
        next_cursor = None
        if len(result_hits) == page_size and result_hits[-1].get("sort"):
            next_cursor = base64.urlsafe_b64encode(
                json.dumps(result_hits[-1]["sort"], separators=(",", ":")).encode()
            ).decode()
        aggregations = response.get("aggregations", {})
        return {
            "total": total,
            "took_ms": response.get("took", 0),
            "page": page,
            "page_size": page_size,
            "next_cursor": next_cursor,
            "facets": {
                name: [
                    {"value": bucket["key"], "count": bucket["doc_count"]}
                    for bucket in aggregation.get("buckets", [])
                ]
                for name, aggregation in aggregations.items()
            },
            "items": [
                {
                    **hit["_source"],
                    "score": hit.get("_score"),
                    "highlights": hit.get("highlight", {}),
                }
                for hit in result_hits
            ],
        }

    def create_build_index(self, build_id: uuid.UUID) -> str:
        self.ensure_index()
        index_name = (
            f"{self.settings.opensearch_index_prefix}-v{self.schema_version}-{build_id.hex[:8]}"
        )
        if self.client.indices.exists(index=index_name):
            return index_name
        self.client.indices.create(
            index=index_name,
            body={
                "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                "mappings": self.client.indices.get_mapping(index=self.physical_index)[
                    self.physical_index
                ]["mappings"],
            },
        )
        return index_name

    def activate_index(self, index_name: str) -> None:
        current = cast(
            dict[str, Any],
            self.client.indices.get_alias(name=self.read_alias)
            if self.client.indices.exists_alias(name=self.read_alias)
            else {},
        )
        current_write = cast(
            dict[str, Any],
            self.client.indices.get_alias(name=self.write_alias)
            if self.client.indices.exists_alias(name=self.write_alias)
            else {},
        )
        actions: list[dict[str, Any]] = [
            {"remove": {"index": name, "alias": self.read_alias}}
            for name in current
            if name != index_name
        ]
        actions.extend(
            {"remove": {"index": name, "alias": self.write_alias}}
            for name in current_write
            if name != index_name
        )
        actions.extend(
            [
                {"add": {"index": index_name, "alias": self.read_alias}},
                {"add": {"index": index_name, "alias": self.write_alias, "is_write_index": True}},
            ]
        )
        self.client.indices.update_aliases(body={"actions": actions})

    def health(self) -> dict[str, Any]:
        return self.client.cluster.health()
