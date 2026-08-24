"""API-Schemas für den Audit-Log (EPIC-0900).

Response-Schemas bilden Kautionsbewegungen als Audit-Einträge ab.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditEintragAntwort(BaseModel):
    """Response für einen einzelnen Audit-Eintrag."""

    id: str
    zeitstempel: datetime
    art: str
    betrag_euro: int
    ausleihe_id: str
    mitglied_id: str
    gegenstand_inventarnummer: str
    pruefprotokoll_id: Optional[str]
    beschreibung: str


class AuditListeAntwort(BaseModel):
    """Response für GET /audit."""

    eintraege: list[AuditEintragAntwort]
    total: int
