"""Datenbankinitialisierung für Leihgut.

SQLite im WAL-Modus, kein externer DB-Server (PRD Rahmenbedingungen).
Engine und Session werden als Abhängigkeiten injiziert.
"""

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

# Import der Modelle sorgt dafür, dass die Tabellen SQLModel bekannt sind
from leihgut.domain import models as _models  # noqa: F401

_DB_URL = "sqlite:///leihgut.db"
_CONNECT_ARGS = {"check_same_thread": False}

engine = create_engine(_DB_URL, connect_args=_CONNECT_ARGS, echo=False)


def erstelle_tabellen() -> None:
    """Erstellt alle Tabellen, falls nicht vorhanden."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI-Dependency: liefert eine DB-Session pro Request."""
    with Session(engine) as session:
        yield session
