from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import make_asgi_app  # pyright: ignore[reportUnknownVariableType]
from starlette.types import ASGIApp

from atlas.api.errors import install_error_handlers
from atlas.api.routes import (
    definitions,
    documents,
    frontier,
    metrics,
    operations,
    runs,
    search,
    system,
    tasks,
)
from atlas.auth import enforce_rate_limit, require_viewer, validate_auth_configuration
from atlas.config import get_settings
from atlas.logging import configure_logging
from atlas.observability import configure_telemetry


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    validate_auth_configuration(settings)
    settings.raw_store_path.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_telemetry(settings)
    app = FastAPI(
        title="Atlas API",
        version="0.1.0",
        description=(
            "Control plane for safe crawl runs, frontier inspection, extraction, and search."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    install_error_handlers(app)
    FastAPIInstrumentor.instrument_app(app)
    if settings.prometheus_endpoint_enabled:
        app.mount("/metrics", cast(ASGIApp, make_asgi_app()))

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "atlas-api"}

    @app.get("/auth/config", tags=["system"])
    def auth_config() -> dict[str, str]:
        current = get_settings()
        if current.auth_mode != "oidc" or not (
            current.cognito_domain and current.cognito_client_id
        ):
            return {"mode": "disabled", "domain": "", "clientId": ""}
        return {
            "mode": "oidc",
            "domain": current.cognito_domain,
            "clientId": current.cognito_client_id,
        }

    prefix = "/api/v1"
    protected = [Depends(require_viewer), Depends(enforce_rate_limit)]
    app.include_router(runs.router, prefix=prefix, dependencies=protected)
    app.include_router(definitions.router, prefix=prefix, dependencies=protected)
    app.include_router(frontier.router, prefix=prefix, dependencies=protected)
    app.include_router(documents.router, prefix=prefix, dependencies=protected)
    app.include_router(metrics.router, prefix=prefix, dependencies=protected)
    app.include_router(search.router, prefix=prefix, dependencies=protected)
    app.include_router(system.router, prefix=prefix, dependencies=protected)
    app.include_router(tasks.router, prefix=prefix, dependencies=protected)
    app.include_router(operations.router, prefix=prefix, dependencies=protected)
    return app
