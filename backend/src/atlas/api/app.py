from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from atlas.api.errors import install_error_handlers
from atlas.api.routes import documents, frontier, metrics, runs, search, system
from atlas.config import get_settings
from atlas.logging import configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    settings.raw_store_path.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
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
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    install_error_handlers(app)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "atlas-api"}

    prefix = "/api/v1"
    app.include_router(runs.router, prefix=prefix)
    app.include_router(frontier.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(metrics.router, prefix=prefix)
    app.include_router(search.router, prefix=prefix)
    app.include_router(system.router, prefix=prefix)
    return app
