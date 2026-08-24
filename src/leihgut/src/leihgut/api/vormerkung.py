"""FastAPI-Router für Vormerkungen.

Issues: 0701, 0702, 0703, 0704, 0705
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session

from leihgut.api.schemas.vormerkung import (
    MitgliedVormerkungAntwort,
    ReservierungInfo,
    VormerkungAnlegen,
    VormerkungAntwort,
)
from leihgut.application import vormerkung as vormerkung_app
from leihgut.application.vormerkung import (
    KategorieNichtGefunden,
    MitgliedNichtGefunden,
    VormerkungBereitsStorniert,
    VormerkungBereitsVorhanden,
    VormerkungNichtGefunden,
    vormerkung_anlegen,
    vormerkung_stornieren,
    vormerkungen_abfragen,
)
from leihgut.infrastructure.datenbank import get_session

router = APIRouter(tags=["Vormerkungen"])

_ALLE_ROLLEN = {"wart", "thekendienst", "mitglied"}
_ANLEGEN_ROLLEN = {"mitglied", "thekendienst"}


def _prüfe_rolle(x_role: str, erlaubt: set[str]) -> None:
    if x_role not in erlaubt:
        raise HTTPException(
            status_code=403,
            detail={"fehler_code": "ROLLE_UNZULAESSIG", "beschreibung": f"Rolle '{x_role}' nicht erlaubt."},
        )


@router.post("/vormerkungen", status_code=201, response_model=VormerkungAntwort, response_model_by_alias=True)
def vormerkung_anlegen_endpoint(
    body: VormerkungAnlegen,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
):
    # 0701
    _prüfe_rolle(x_role, _ANLEGEN_ROLLEN)
    heute = vormerkung_app._datumsquelle.heute()
    try:
        result = vormerkung_anlegen(session, body.mitglied_id, body.kategorie_id, heute)
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
    except VormerkungBereitsVorhanden:
        raise HTTPException(
            status_code=409,
            detail={"fehler_code": "VORMERKUNG_BEREITS_VORHANDEN", "beschreibung": "Mitglied hat bereits eine Vormerkung für diese Kategorie. (BR-28)"},
        )

    res_info = None
    if result["reservierung"]:
        res_info = ReservierungInfo(
            gegenstandId=result["reservierung"]["gegenstandId"],
            reserviertBis=result["reservierung"]["reserviertBis"],
        )

    return VormerkungAntwort(
        vormerkungId=result["vormerkungId"],
        mitgliedId=result["mitgliedId"],
        kategorieId=result["kategorieId"],
        kategorieName=result["kategorieName"],
        eingangszeit=result["eingangszeit"],
        positionInSchlange=result["positionInSchlange"],
        reservierung=res_info,
        hinweis=result["hinweis"],
    )


@router.delete("/vormerkungen/{vormerkung_id}", status_code=204)
def vormerkung_stornieren_endpoint(
    vormerkung_id: uuid.UUID,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
):
    # 0702
    _prüfe_rolle(x_role, _ALLE_ROLLEN)
    heute = vormerkung_app._datumsquelle.heute()
    try:
        vormerkung_stornieren(session, vormerkung_id, heute)
    except VormerkungNichtGefunden:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "VORMERKUNG_NICHT_GEFUNDEN", "beschreibung": "Keine Vormerkung mit dieser ID."},
        )
    except VormerkungBereitsStorniert:
        raise HTTPException(
            status_code=409,
            detail={"fehler_code": "VORMERKUNG_BEREITS_STORNIERT", "beschreibung": "Vormerkung ist bereits storniert."},
        )


@router.get("/mitglieder/{mitglied_id}/vormerkungen", response_model=list[MitgliedVormerkungAntwort], response_model_by_alias=True)
def mitglied_vormerkungen_abfragen(
    mitglied_id: uuid.UUID,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
):
    # 0705
    _prüfe_rolle(x_role, _ALLE_ROLLEN)
    heute = vormerkung_app._datumsquelle.heute()
    ergebnis = vormerkungen_abfragen(session, mitglied_id, heute)

    antworten = []
    for item in ergebnis:
        res_info = None
        if item["reservierung"]:
            res_info = ReservierungInfo(
                gegenstandId=item["reservierung"]["gegenstandId"],
                reserviertBis=item["reservierung"]["reserviertBis"],
            )
        antworten.append(
            MitgliedVormerkungAntwort(
                vormerkungId=item["vormerkungId"],
                kategorieId=item["kategorieId"],
                kategorieName=item["kategorieName"],
                eingangszeit=item["eingangszeit"],
                status=item["status"],
                positionInSchlange=item["positionInSchlange"],
                reservierung=res_info,
            )
        )
    return antworten
