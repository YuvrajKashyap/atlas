from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from atlas.api.app import create_app
from atlas.db import SessionLocal, engine
from atlas.models import Base


def _truncate_database() -> None:
    table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_session() -> Generator[Session]:
    _truncate_database()
    with SessionLocal() as session:
        yield session
    _truncate_database()


@pytest.fixture
def api_client(db_session: Session) -> Generator[TestClient]:
    _ = db_session
    with TestClient(create_app()) as client:
        yield client
