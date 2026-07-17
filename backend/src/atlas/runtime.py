import os
import sys
from collections.abc import Callable
from urllib.parse import quote_plus


def configure_database_url() -> None:
    if os.getenv("DATABASE_URL"):
        return
    host = os.getenv("ATLAS_DB_HOST")
    user = os.getenv("ATLAS_DB_USER")
    password = os.getenv("ATLAS_DB_PASSWORD")
    database = os.getenv("ATLAS_DB_NAME", "atlas")
    port = os.getenv("ATLAS_DB_PORT", "5432")
    if not (host and user and password):
        return
    os.environ["DATABASE_URL"] = (
        f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{quote_plus(database)}?sslmode=require"
    )


def migrate() -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from atlas.config import get_settings

    configure_database_url()
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(4183157201)"))
        try:
            configuration = Config("alembic.ini")
            configuration.attributes["connection"] = connection
            command.upgrade(configuration, "head")
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(4183157201)"))
    engine.dispose()


def run_api() -> None:
    import uvicorn

    migrate()
    uvicorn.run(
        "atlas.api.app:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - container listener is isolated by the task SG
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


def run_scheduler() -> None:
    migrate()
    from atlas.scheduler import main

    main()


def run_worker() -> None:
    migrate()
    from atlas.worker import main

    main()


def main() -> None:
    actions: dict[str, Callable[[], None]] = {
        "api": run_api,
        "migrate": migrate,
        "scheduler": run_scheduler,
        "worker": run_worker,
    }
    requested = sys.argv[1] if len(sys.argv) > 1 else ""
    action = actions.get(requested)
    if action is None:
        raise SystemExit("usage: python -m atlas.runtime [api|migrate|scheduler|worker]")
    configure_database_url()
    action()


if __name__ == "__main__":
    main()
