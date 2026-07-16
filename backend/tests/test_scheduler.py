import re
import uuid

from atlas.scheduler import build_job_id


def test_rq_job_id_uses_only_supported_characters() -> None:
    job_id = build_job_id(uuid.UUID("a9b58aa4-1ecc-4288-8423-e1aac4efef5f"), 3)

    assert job_id == "fetch-a9b58aa4-1ecc-4288-8423-e1aac4efef5f-3"
    assert re.fullmatch(r"[A-Za-z0-9_-]+", job_id)
