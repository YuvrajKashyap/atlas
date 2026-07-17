import gzip
import uuid
from pathlib import Path
from typing import Any, Protocol, cast

import boto3
from botocore.client import BaseClient

from atlas.config import Settings


class BlobStore(Protocol):
    def put_html(self, run_id: uuid.UUID, attempt_id: uuid.UUID, body: bytes) -> str: ...

    def get_html(self, key: str) -> bytes: ...


class LocalBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put_html(self, run_id: uuid.UUID, attempt_id: uuid.UUID, body: bytes) -> str:
        relative = Path(str(run_id)) / f"{attempt_id}.html.gz"
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(destination, "wb", compresslevel=6) as stream:
            stream.write(body)
        return relative.as_posix()

    def get_html(self, key: str) -> bytes:
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in candidate.parents:
            raise ValueError("Blob key escapes the configured store")
        with gzip.open(candidate, "rb") as stream:
            return stream.read()


class S3BlobStore:
    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = "raw",
        kms_key_id: str = "",
        client: BaseClient | None = None,
    ) -> None:
        if not bucket:
            raise ValueError("S3 blob storage requires a bucket")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.kms_key_id = kms_key_id
        self.client = client or boto3.client("s3")

    def put_html(self, run_id: uuid.UUID, attempt_id: uuid.UUID, body: bytes) -> str:
        key = f"{self.prefix}/runs/{run_id}/attempts/{attempt_id}.html.gz"
        parameters: dict[str, object] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": gzip.compress(body, compresslevel=6),
            "ContentType": "text/html",
            "ContentEncoding": "gzip",
            "ServerSideEncryption": "aws:kms" if self.kms_key_id else "AES256",
        }
        if self.kms_key_id:
            parameters["SSEKMSKeyId"] = self.kms_key_id
        self.client.put_object(**parameters)
        return key

    def get_html(self, key: str) -> bytes:
        if not key.startswith(f"{self.prefix}/") or ".." in key.split("/"):
            raise ValueError("Blob key escapes the configured prefix")
        response = cast(dict[str, Any], self.client.get_object(Bucket=self.bucket, Key=key))
        body = cast(bytes, response["Body"].read())
        return gzip.decompress(body)


def get_blob_store(settings: Settings) -> BlobStore:
    if settings.blob_store_backend == "s3":
        return S3BlobStore(
            settings.s3_bucket,
            prefix=settings.s3_prefix,
            kms_key_id=settings.s3_kms_key_id,
        )
    if settings.blob_store_backend != "local":
        raise ValueError(f"Unsupported blob store backend: {settings.blob_store_backend}")
    return LocalBlobStore(settings.raw_store_path)
