from typing import cast

import httpx
from fastapi.testclient import TestClient

from atlas.api.app import create_app


def test_health_endpoint() -> None:
    with TestClient(create_app()) as client:
        response = cast(httpx.Response, client.get("/health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "atlas-api"}


def test_openapi_exposes_control_plane_resources() -> None:
    with TestClient(create_app()) as client:
        response = cast(httpx.Response, client.get("/openapi.json"))

    assert response.status_code == 200
    payload = cast(dict[str, object], response.json())
    paths = cast(dict[str, object], payload["paths"])
    assert "/api/v1/crawl-runs" in paths
    assert "/api/v1/frontier" in paths
    assert "/api/v1/documents" in paths
    assert "/api/v1/search" in paths
    assert "/api/v1/system/status" in paths
