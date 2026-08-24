"""Application Use Cases für EPIC-0100: Katalog verwalten.

Reine Integration (IOSP): orchestriert DB-Zugriffe und Domänenregel-Aufrufe.
Keine eigene Geschäftslogik. Eigene Exceptions — kein FastAPI-Import.
"""

import uuid
from typing import Optional

from sqlmodel import Session, select

from leihgut.domain.models import Gegenstand, GegenstandZustand, Kategorie


# ─────────────────────────────────────────────
#  Anwendungsausnahmen
# ─────────────────────────────────────────────


class KategorieNameDoppelt(Exception):
    def __init__(self, name: str) -> None:
        self.name = name


class KategorieNichtGefunden(Exception):
    def __init__(self, kategorie_id: str) -> None:
        self.kategorie_id = kategorie_id


class InventarnummerDoppelt(Exception):
    def __init__(self, inventarnummer: str) -> None:
        self.inventarnummer = inventarnummer


class GegenstandNichtGefunden(Exception):
    def __init__(self, inventarnummer: str) -> None:
        self.inventarnummer = inventarnummer


# ─────────────────────────────────────────────
#  Kategorie Use Cases
# ─────────────────────────────────────────────


def anlegen_kategorie(
    session: Session,
    name: str,
    leihdauer_tage: int,
    wartungsintervall_ausleihen: int,
    einweisungspflichtig: bool,
) -> Kategorie:
    """UC-0101: Neue Kategorie anlegen."""
    existing = session.exec(select(Kategorie).where(Kategorie.name == name)).first()
    if existing:
        raise KategorieNameDoppelt(name)
    kategorie = Kategorie(
        name=name,
        leihdauer_tage=leihdauer_tage,
        wartungsintervall_ausleihen=wartungsintervall_ausleihen,
        einweisungspflichtig=einweisungspflichtig,
    )
    session.add(kategorie)
    session.commit()
    session.refresh(kategorie)
    return kategorie


def abfragen_kategorien(
    session: Session,
    einweisungspflichtig: Optional[bool] = None,
) -> list[Kategorie]:
    """UC-0104: Alle Kategorien abfragen, optional gefiltert."""
    statement = select(Kategorie)
    if einweisungspflichtig is not None:
        statement = statement.where(Kategorie.einweisungspflichtig == einweisungspflichtig)
    return list(session.exec(statement).all())


def abfragen_kategorie(session: Session, kategorie_id: uuid.UUID) -> Kategorie:
    """UC-0104: Einzelne Kategorie abrufen."""
    kategorie = session.get(Kategorie, kategorie_id)
    if not kategorie:
        raise KategorieNichtGefunden(str(kategorie_id))
    return kategorie


def aktualisieren_kategorie(
    session: Session,
    kategorie_id: uuid.UUID,
    name: str,
    leihdauer_tage: int,
    wartungsintervall_ausleihen: int,
    einweisungspflichtig: bool,
) -> Kategorie:
    """UC-0103: Kategorie vollständig aktualisieren (PUT)."""
    kategorie = session.get(Kategorie, kategorie_id)
    if not kategorie:
        raise KategorieNichtGefunden(str(kategorie_id))
    existing = session.exec(
        select(Kategorie)
        .where(Kategorie.name == name)
        .where(Kategorie.id != kategorie_id)
    ).first()
    if existing:
        raise KategorieNameDoppelt(name)
    kategorie.name = name
    kategorie.leihdauer_tage = leihdauer_tage
    kategorie.wartungsintervall_ausleihen = wartungsintervall_ausleihen
    kategorie.einweisungspflichtig = einweisungspflichtig
    session.add(kategorie)
    session.commit()
    session.refresh(kategorie)
    return kategorie


# ─────────────────────────────────────────────
#  Gegenstand Use Cases
# ─────────────────────────────────────────────


def anlegen_gegenstand(
    session: Session,
    inventarnummer: str,
    kategorie_id: uuid.UUID,
    wiederbeschaffungswert: int,
) -> tuple[Gegenstand, Kategorie]:
    """UC-0102: Neuen Gegenstand anlegen."""
    existing = session.exec(
        select(Gegenstand).where(Gegenstand.inventarnummer == inventarnummer)
    ).first()
    if existing:
        raise InventarnummerDoppelt(inventarnummer)
    kategorie = session.get(Kategorie, kategorie_id)
    if not kategorie:
        raise KategorieNichtGefunden(str(kategorie_id))
    gegenstand = Gegenstand(
        inventarnummer=inventarnummer,
        kategorie_id=kategorie_id,
        wiederbeschaffungswert_euro=wiederbeschaffungswert,
    )
    session.add(gegenstand)
    session.commit()
    session.refresh(gegenstand)
    # Kategorie nach Commit neu laden (Objekte werden nach Commit expired)
    kategorie = session.get(Kategorie, gegenstand.kategorie_id)
    return gegenstand, kategorie


def abfragen_gegenstaende(
    session: Session,
    kategorie_id: Optional[uuid.UUID] = None,
    zustand: Optional[GegenstandZustand] = None,
) -> list[tuple[Gegenstand, Kategorie]]:
    """UC-0104: Alle Gegenstände abfragen, optional gefiltert."""
    statement = select(Gegenstand, Kategorie).join(Kategorie)
    if kategorie_id is not None:
        statement = statement.where(Gegenstand.kategorie_id == kategorie_id)
    if zustand is not None:
        statement = statement.where(Gegenstand.zustand == zustand)
    return list(session.exec(statement).all())


def abfragen_gegenstand(
    session: Session, inventarnummer: str
) -> tuple[Gegenstand, Kategorie]:
    """UC-0104: Einzelnen Gegenstand per Inventarnummer abrufen."""
    result = session.exec(
        select(Gegenstand, Kategorie)
        .join(Kategorie)
        .where(Gegenstand.inventarnummer == inventarnummer)
    ).first()
    if not result:
        raise GegenstandNichtGefunden(inventarnummer)
    return result


def aktualisieren_gegenstand(
    session: Session,
    inventarnummer: str,
    wiederbeschaffungswert: Optional[int],
) -> tuple[Gegenstand, Kategorie]:
    """UC-0103: Gegenstand partiell aktualisieren (PATCH)."""
    result = session.exec(
        select(Gegenstand, Kategorie)
        .join(Kategorie)
        .where(Gegenstand.inventarnummer == inventarnummer)
    ).first()
    if not result:
        raise GegenstandNichtGefunden(inventarnummer)
    gegenstand, _ = result
    if wiederbeschaffungswert is not None:
        gegenstand.wiederbeschaffungswert_euro = wiederbeschaffungswert
    session.add(gegenstand)
    session.commit()
    session.refresh(gegenstand)
    kategorie = session.get(Kategorie, gegenstand.kategorie_id)
    return gegenstand, kategorie
