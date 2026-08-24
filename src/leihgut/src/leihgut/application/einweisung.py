"""Application Use Cases für Einweisungen und Mitglieder.

Issue: 0201, 0202, 0203
IOSP: reine Integration — orchestriert DB-Zugriff, keine Berechnungslogik.
"""

import uuid
from datetime import date
from typing import Optional

from sqlmodel import Session, select

from leihgut.domain.models import Einweisung, Kategorie, Mitglied


# ─────────────────────────────────────────────
#  Exceptions
# ─────────────────────────────────────────────


class MitgliedNichtGefunden(Exception):
    pass


class KategorieNichtGefunden(Exception):
    pass


class EinweisungBereitsVorhanden(Exception):
    pass


class EinweisungNichtGefunden(Exception):
    pass


# ─────────────────────────────────────────────
#  Mitglied
# ─────────────────────────────────────────────


def anlegen_mitglied(session: Session, name: str) -> Mitglied:
    mitglied = Mitglied(name=name)
    session.add(mitglied)
    session.commit()
    session.refresh(mitglied)
    return mitglied


def abfragen_mitglied(session: Session, mitglied_id: uuid.UUID) -> Mitglied:
    mitglied = session.get(Mitglied, mitglied_id)
    if not mitglied:
        raise MitgliedNichtGefunden(str(mitglied_id))
    return mitglied


# ─────────────────────────────────────────────
#  Einweisung (BR-08)
# ─────────────────────────────────────────────


def hat_einweisung(
    session: Session,
    mitglied_id: uuid.UUID,
    kategorie_id: uuid.UUID,
) -> bool:
    """BR-08: Prüft ob Mitglied eine gültige Einweisung für die Kategorie hat."""
    stmt = select(Einweisung).where(
        Einweisung.mitglied_id == mitglied_id,
        Einweisung.kategorie_id == kategorie_id,
    )
    return session.exec(stmt).first() is not None


def anlegen_einweisung(
    session: Session,
    mitglied_id: uuid.UUID,
    kategorie_id: uuid.UUID,
    datum: date,
    dokumentiert_von: str,
) -> Einweisung:
    """BR-08: Dokumentiert eine Einweisung. Fehler wenn bereits vorhanden."""
    mitglied = session.get(Mitglied, mitglied_id)
    if not mitglied:
        raise MitgliedNichtGefunden(str(mitglied_id))

    kategorie = session.get(Kategorie, kategorie_id)
    if not kategorie:
        raise KategorieNichtGefunden(str(kategorie_id))

    if hat_einweisung(session, mitglied_id, kategorie_id):
        raise EinweisungBereitsVorhanden(
            f"Mitglied {mitglied_id} hat bereits eine Einweisung für Kategorie {kategorie_id}"
        )

    einweisung = Einweisung(
        mitglied_id=mitglied_id,
        kategorie_id=kategorie_id,
        datum=datum,
        dokumentiert_von=dokumentiert_von,
    )
    session.add(einweisung)
    session.commit()
    session.refresh(einweisung)
    return einweisung


def abfragen_einweisungen(
    session: Session,
    mitglied_id: Optional[uuid.UUID] = None,
    kategorie_id: Optional[uuid.UUID] = None,
) -> list[Einweisung]:
    stmt = select(Einweisung)
    if mitglied_id:
        stmt = stmt.where(Einweisung.mitglied_id == mitglied_id)
    if kategorie_id:
        stmt = stmt.where(Einweisung.kategorie_id == kategorie_id)
    return list(session.exec(stmt).all())


def loeschen_einweisung(session: Session, einweisung_id: uuid.UUID) -> None:
    """Story 0203: Einweisung widerrufen."""
    einweisung = session.get(Einweisung, einweisung_id)
    if not einweisung:
        raise EinweisungNichtGefunden(str(einweisung_id))
    session.delete(einweisung)
    session.commit()
