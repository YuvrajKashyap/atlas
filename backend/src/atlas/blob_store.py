import gzip
import uuid
from pathlib import Path


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
