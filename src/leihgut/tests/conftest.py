"""Pytest-Konfiguration und gemeinsame Fixtures."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from leihgut.main import app
from leihgut.infrastructure.datenbank import get_session
from leihgut.infrastructure.datum import FixesDatum
from datetime import date


@pytest.fixture(name="session")
def session_fixture():
    """In-Memory SQLite für Tests — isoliert, kein Datei-I/O."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    """TestClient mit überschriebener DB-Session."""

    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="heute")
def heute_fixture():
    """Festes Testdatum: 2026-09-01."""
    return date(2026, 9, 1)


@pytest.fixture(name="datumsquelle")
def datumsquelle_fixture(heute):
    return FixesDatum(heute)
