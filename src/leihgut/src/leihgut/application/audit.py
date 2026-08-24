"""Application Use Cases für EPIC-0900: Audit-Log.

Reine Integration (IOSP): orchestriert DB-Zugriffe, keine eigene Geschäftslogik.
Service-Funktionen werden von anderen Use Cases (Wave 5+) aufgerufen.
BR-22: Kautionsbewegungen und Zustandswechsel sind append-only.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from leihgut.domain.models import (
    AuditEintrag,
    AuditTyp,
    Ausleihe,
    Gegenstand,
    Kautionsbewegung,
    KautionsbewegungArt,
)


# ─────────────────────────────────────────────
#  Anwendungsausnahmen
# ─────────────────────────────────────────────


class AuditEintragNichtGefunden(Exception):
    def __init__(self, eintrag_id: str) -> None:
        self.eintrag_id = eintrag_id


class ZeitraumUngueltig(Exception):
    pass


# ─────────────────────────────────────────────
#  Service-Funktionen (von anderen Use Cases genutzt)
# ─────────────────────────────────────────────


def erfasse_kautionsbewegung(
    session: Session,
    ausleihe_id: uuid.UUID,
    art: KautionsbewegungArt,
    betrag: int,
    zeitstempel: datetime,
    referenz_id: Optional[uuid.UUID] = None,
) -> Kautionsbewegung:
    """BR-22: Legt eine Kautionsbewegung an (append-only)."""
    bewegung = Kautionsbewegung(
        ausleihe_id=ausleihe_id,
        art=art,
        betrag=betrag,
        zeitstempel=zeitstempel,
        referenz_id=referenz_id,
    )
    session.add(bewegung)
    session.commit()
    session.refresh(bewegung)
    return bewegung


def erfasse_zustandswechsel(
    session: Session,
    gegenstand_id: uuid.UUID,
    altzustand: str,
    neuzustand: str,
    zeitstempel: datetime,
    ausleihe_id: Optional[uuid.UUID] = None,
    pruefprotokoll_id: Optional[uuid.UUID] = None,
) -> AuditEintrag:
    """Legt einen Audit-Eintrag für einen Zustandswechsel an."""
    eintrag = AuditEintrag(
        zeitstempel=zeitstempel,
        typ=AuditTyp.zustandswechsel,
        gegenstand_id=gegenstand_id,
        altzustand=altzustand,
        neuzustand=neuzustand,
        ausleihe_id=ausleihe_id,
        pruefprotokoll_id=pruefprotokoll_id,
    )
    session.add(eintrag)
    session.commit()
    session.refresh(eintrag)
    return eintrag


# ─────────────────────────────────────────────
#  Hilfsfunktionen
# ─────────────────────────────────────────────


_BESCHREIBUNGEN: dict[KautionsbewegungArt, str] = {
    KautionsbewegungArt.hinterlegung: "Kaution hinterlegt bei Ausgabe",
    KautionsbewegungArt.abzug: "Kautionsabzug nach Prüfung",
    KautionsbewegungArt.freigabe: "Kaution freigegeben nach Prüfung",
    KautionsbewegungArt.einbehaltung: "Kaution einbehalten (Verlust)",
}


def _bewegung_zu_dict(
    bewegung: Kautionsbewegung,
    ausleihe: Ausleihe,
    gegenstand: Gegenstand,
) -> dict:
    pruefprotokoll_id = (
        str(bewegung.referenz_id)
        if bewegung.art != KautionsbewegungArt.hinterlegung and bewegung.referenz_id
        else None
    )
    return {
        "id": str(bewegung.id),
        "zeitstempel": bewegung.zeitstempel,
        "art": bewegung.art.value,
        "betrag_euro": bewegung.betrag,
        "ausleihe_id": str(bewegung.ausleihe_id),
        "mitglied_id": str(ausleihe.mitglied_id),
        "gegenstand_inventarnummer": gegenstand.inventarnummer,
        "pruefprotokoll_id": pruefprotokoll_id,
        "beschreibung": _BESCHREIBUNGEN.get(bewegung.art, bewegung.art.value),
    }


def _basis_statement():
    return (
        select(Kautionsbewegung, Ausleihe, Gegenstand)
        .join(Ausleihe, Kautionsbewegung.ausleihe_id == Ausleihe.id)
        .join(Gegenstand, Ausleihe.gegenstand_id == Gegenstand.id)
    )


# ─────────────────────────────────────────────
#  Abfrage-Logik (UC-0903)
# ─────────────────────────────────────────────


def abfragen_audit_eintraege(
    session: Session,
    ausleihe_id: Optional[uuid.UUID] = None,
    mitglied_id: Optional[uuid.UUID] = None,
    gegenstand_inventarnummer: Optional[str] = None,
    art: Optional[KautionsbewegungArt] = None,
    von: Optional[date] = None,
    bis: Optional[date] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """UC-0903: Kautionsbewegungen abfragen mit Filtern und Paginierung."""
    if von is not None and bis is not None and von > bis:
        raise ZeitraumUngueltig()

    statement = _basis_statement()

    if ausleihe_id is not None:
        statement = statement.where(Kautionsbewegung.ausleihe_id == ausleihe_id)
    if mitglied_id is not None:
        statement = statement.where(Ausleihe.mitglied_id == mitglied_id)
    if gegenstand_inventarnummer is not None:
        statement = statement.where(Gegenstand.inventarnummer == gegenstand_inventarnummer)
    if art is not None:
        statement = statement.where(Kautionsbewegung.art == art)
    if von is not None:
        statement = statement.where(
            Kautionsbewegung.zeitstempel >= datetime.combine(von, datetime.min.time())
        )
    if bis is not None:
        statement = statement.where(
            Kautionsbewegung.zeitstempel < datetime.combine(bis + timedelta(days=1), datetime.min.time())
        )

    all_results = list(session.exec(statement).all())
    total = len(all_results)
    paged = all_results[offset : offset + limit]

    eintraege = [_bewegung_zu_dict(b, a, g) for b, a, g in paged]
    return eintraege, total


def abfragen_audit_eintrag(session: Session, eintrag_id: uuid.UUID) -> dict:
    """UC-0903: Einzelne Kautionsbewegung per ID abrufen."""
    result = session.exec(
        _basis_statement().where(Kautionsbewegung.id == eintrag_id)
    ).first()
    if not result:
        raise AuditEintragNichtGefunden(str(eintrag_id))
    bewegung, ausleihe, gegenstand = result
    return _bewegung_zu_dict(bewegung, ausleihe, gegenstand)
