"""API-Router für EPIC-0900: Audit-Log.

Nur lesende Endpunkte (BR-22: append-only).
Rollen: wart, thekendienst.
"""

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlmodel import Session

from leihgut.api.schemas.audit import AuditEintragAntwort, AuditListeAntwort
from leihgut.application.audit import (
    AuditEintragNichtGefunden,
    ZeitraumUngueltig,
    abfragen_audit_eintrag,
    abfragen_audit_eintraege,
)
from leihgut.domain.models import KautionsbewegungArt
from leihgut.infrastructure.datenbank import get_session

router = APIRouter(prefix="/audit", tags=["audit"])

_ROLLEN_LESEN = {"wart", "thekendienst"}


def _pruefe_lesen(rolle: str) -> None:
    if rolle not in _ROLLEN_LESEN:
        raise HTTPException(
            status_code=403,
            detail={
                "fehler_code": "ROLLE_UNZULAESSIG",
                "beschreibung": f"Rolle '{rolle}' hat keine Leseberechtigung.",
                "kontext": {"rolle": rolle},
            },
        )


@router.get("", response_model=AuditListeAntwort)
def liste_audit_eintraege(
    ausleihe_id: Optional[uuid.UUID] = Query(default=None),
    mitglied_id: Optional[uuid.UUID] = Query(default=None),
    gegenstand_inventarnummer: Optional[str] = Query(default=None),
    art: Optional[KautionsbewegungArt] = Query(default=None),
    von: Optional[date] = Query(default=None),
    bis: Optional[date] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> AuditListeAntwort:
    """GET /audit — Audit-Einträge (Kautionsbewegungen) abfragen. (0903)"""
    _pruefe_lesen(x_role)
    try:
        eintraege, total = abfragen_audit_eintraege(
            session,
            ausleihe_id=ausleihe_id,
            mitglied_id=mitglied_id,
            gegenstand_inventarnummer=gegenstand_inventarnummer,
            art=art,
            von=von,
            bis=bis,
            limit=limit,
            offset=offset,
        )
    except ZeitraumUngueltig:
        raise HTTPException(
            status_code=400,
            detail={
                "fehler_code": "ZEITRAUM_UNGUELTIG",
                "beschreibung": "'von' darf nicht nach 'bis' liegen.",
                "kontext": {},
            },
        )
    return AuditListeAntwort(
        eintraege=[AuditEintragAntwort(**e) for e in eintraege],
        total=total,
    )


@router.get("/{eintrag_id}", response_model=AuditEintragAntwort)
def hole_audit_eintrag(
    eintrag_id: uuid.UUID,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> AuditEintragAntwort:
    """GET /audit/{id} — Einzelnen Audit-Eintrag abrufen. (0903)"""
    _pruefe_lesen(x_role)
    try:
        eintrag = abfragen_audit_eintrag(session, eintrag_id)
    except AuditEintragNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "fehler_code": "AUDIT_EINTRAG_NICHT_GEFUNDEN",
                "beschreibung": f"Audit-Eintrag '{exc.eintrag_id}' nicht gefunden.",
                "kontext": {"id": exc.eintrag_id},
            },
        ) from exc
    return AuditEintragAntwort(**eintrag)
