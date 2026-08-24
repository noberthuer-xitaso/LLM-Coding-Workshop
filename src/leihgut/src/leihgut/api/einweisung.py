"""FastAPI-Router für Einweisungen und Mitglieder.

Issues: 0201, 0202, 0203
Rollen: wart (schreiben), wart + thekendienst (lesen)
"""

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session

from leihgut.api.schemas.einweisung import (
    EinweisungAnlegen,
    EinweisungAntwort,
    MitgliedAnlegen,
    MitgliedAntwort,
)
from leihgut.application.einweisung import (
    EinweisungBereitsVorhanden,
    EinweisungNichtGefunden,
    KategorieNichtGefunden,
    MitgliedNichtGefunden,
    abfragen_einweisungen,
    abfragen_mitglied,
    anlegen_einweisung,
    anlegen_mitglied,
    loeschen_einweisung,
)
from leihgut.domain.models import Kategorie
from leihgut.infrastructure.datenbank import get_session
from leihgut.infrastructure.datum import SystemDatumsQuelle

router = APIRouter(tags=["Einweisungen & Mitglieder"])

_LESE_ROLLEN = {"wart", "thekendienst"}
_SCHREIB_ROLLEN = {"wart"}


def _prüfe_rolle(x_role: str, erlaubt: set[str]) -> None:
    if x_role not in erlaubt:
        raise HTTPException(
            status_code=403,
            detail={"fehler_code": "ROLLE_UNZULAESSIG", "beschreibung": f"Rolle '{x_role}' nicht erlaubt."},
        )


# ─────────────────────────────────────────────
#  Mitglieder
# ─────────────────────────────────────────────


@router.post("/mitglieder", status_code=201, response_model=MitgliedAntwort, response_model_by_alias=True)
def mitglied_anlegen(
    body: MitgliedAnlegen,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
):
    _prüfe_rolle(x_role, _LESE_ROLLEN)  # wart oder thekendienst dürfen anlegen
    mitglied = anlegen_mitglied(session, body.name)
    return MitgliedAntwort.from_mitglied(mitglied)


@router.get("/mitglieder/{mitglied_id}", response_model=MitgliedAntwort, response_model_by_alias=True)
def mitglied_abfragen(
    mitglied_id: uuid.UUID,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
):
    _prüfe_rolle(x_role, _LESE_ROLLEN)
    try:
        mitglied = abfragen_mitglied(session, mitglied_id)
    except MitgliedNichtGefunden:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "MITGLIED_NICHT_GEFUNDEN", "beschreibung": "Kein Mitglied mit dieser ID."},
        )
    return MitgliedAntwort.from_mitglied(mitglied)


@router.get(
    "/mitglieder/{mitglied_id}/einweisungen",
    response_model=list[EinweisungAntwort],
    response_model_by_alias=True,
)
def mitglied_einweisungen_abfragen(
    mitglied_id: uuid.UUID,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
):
    _prüfe_rolle(x_role, _LESE_ROLLEN)
    try:
        abfragen_mitglied(session, mitglied_id)
    except MitgliedNichtGefunden:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "MITGLIED_NICHT_GEFUNDEN", "beschreibung": "Kein Mitglied mit dieser ID."},
        )
    einweisungen = abfragen_einweisungen(session, mitglied_id=mitglied_id)
    return [
        EinweisungAntwort.from_einweisung(e, e.kategorie.name if e.kategorie else "")
        for e in einweisungen
    ]


# ─────────────────────────────────────────────
#  Einweisungen
# ─────────────────────────────────────────────


@router.post("/einweisungen", status_code=201, response_model=EinweisungAntwort, response_model_by_alias=True)
def einweisung_anlegen(
    body: EinweisungAnlegen,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
):
    _prüfe_rolle(x_role, _SCHREIB_ROLLEN)
    heute = SystemDatumsQuelle().heute()
    try:
        einweisung = anlegen_einweisung(
            session,
            mitglied_id=body.mitglied_id,
            kategorie_id=body.kategorie_id,
            datum=heute,
            dokumentiert_von=body.dokumentiert_von or "wart",
        )
    except MitgliedNichtGefunden:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "MITGLIED_NICHT_GEFUNDEN", "beschreibung": "Kein Mitglied mit dieser ID."},
        )
    except KategorieNichtGefunden:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "KATEGORIE_NICHT_GEFUNDEN", "beschreibung": "Keine Kategorie mit dieser ID."},
        )
    except EinweisungBereitsVorhanden:
        raise HTTPException(
            status_code=409,
            detail={"fehler_code": "EINWEISUNG_BEREITS_VORHANDEN", "beschreibung": "Mitglied hat bereits eine Einweisung für diese Kategorie."},
        )

    session.refresh(einweisung)
    kategorie = session.get(Kategorie, einweisung.kategorie_id)
    return EinweisungAntwort.from_einweisung(einweisung, kategorie.name if kategorie else "")


@router.get("/einweisungen", response_model=list[EinweisungAntwort], response_model_by_alias=True)
def einweisungen_abfragen(
    mitglied_id: Optional[uuid.UUID] = None,
    kategorie_id: Optional[uuid.UUID] = None,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
):
    _prüfe_rolle(x_role, _LESE_ROLLEN)
    einweisungen = abfragen_einweisungen(session, mitglied_id=mitglied_id, kategorie_id=kategorie_id)
    return [
        EinweisungAntwort.from_einweisung(e, e.kategorie.name if e.kategorie else "")
        for e in einweisungen
    ]


@router.delete("/einweisungen/{einweisung_id}", status_code=204)
def einweisung_loeschen(
    einweisung_id: uuid.UUID,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
):
    _prüfe_rolle(x_role, _SCHREIB_ROLLEN)
    try:
        loeschen_einweisung(session, einweisung_id)
    except EinweisungNichtGefunden:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "EINWEISUNG_NICHT_GEFUNDEN", "beschreibung": "Keine Einweisung mit dieser ID."},
        )
