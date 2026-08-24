"""API-Router für EPIC-0300: Ausleihe + Verlängerung, EPIC-0800: Mitgliedersperre.

Issue: 0301, 0302, 0303, 0304, 0801, 0802
HTTP-Routing, Serialisierung und Rollenkontrolle gemäß Interface Contract.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlmodel import Session, select

from leihgut.api.schemas.ausleihe import (
    AusgabefaehigkeitAntwort,
    AusleiheAnlegen,
    AusleiheAnlegenAntwort,
    AusleiheAntwort,
    SperrstatusAntwort,
)
from leihgut.application import ausleihe as ausleihe_app
from leihgut.application.ausleihe import (
    AusleiheNichtAktiv,
    AusleiheNichtGefunden,
    AusleiheUeberfaellig,
    BereitsVerlaengert,
    EinweisungFehlt,
    GegenstandNichtVerfuegbar,
    GegenstandWartungsfaellig,
    MitgliedGesperrt,
    MitgliedNichtGefunden,
    AusleihlimitErreicht,
    VormerkungOffen,
    ausleihe_abfragen,
    ausleihe_anlegen,
    ausleihe_verlaengern,
    ausleihen_abfragen_fuer_mitglied,
    prüfe_ausgabefaehigkeit,
    sperrstatus_abfragen,
)
from leihgut.application.katalog import GegenstandNichtGefunden
from leihgut.domain.models import Gegenstand
from leihgut.infrastructure.datenbank import get_session

router = APIRouter()

_ROLLEN_THEKE = {"thekendienst"}
_ROLLEN_LESEN = {"wart", "thekendienst"}
_ROLLEN_MITGLIED = {"wart", "thekendienst", "mitglied"}
_ROLLEN_VERLAENGERN = {"thekendienst", "mitglied"}


def _pruefe_rolle(rolle: str, erlaubte: set[str]) -> None:
    if rolle not in erlaubte:
        raise HTTPException(
            status_code=403,
            detail={
                "fehler_code": "ROLLE_UNZULAESSIG",
                "beschreibung": f"Rolle '{rolle}' hat keine Berechtigung.",
                "kontext": {"rolle": rolle},
            },
        )


def _ausleihe_zu_antwort(ausleihe, inventarnummer: str, heute) -> AusleiheAntwort:
    from datetime import date as date_type
    ueberfaellig = getattr(ausleihe, "ueberfaellig", False)
    return AusleiheAntwort(
        ausleiheId=str(ausleihe.id),
        gegenstandId=inventarnummer,
        mitgliedId=str(ausleihe.mitglied_id),
        ausgabedatum=ausleihe.ausgabe_datum,
        rueckgabefrist=ausleihe.rueckgabefrist,
        kautionsbetrag=ausleihe.kaution_betrag,
        verlaengert=ausleihe.verlaengert,
        status=ausleihe.status.value,
        ueberfaellig=ueberfaellig,
    )


def _hole_inventarnummer(session: Session, ausleihe) -> str:
    gegenstand = session.get(Gegenstand, ausleihe.gegenstand_id)
    return gegenstand.inventarnummer if gegenstand else str(ausleihe.gegenstand_id)


# ─────────────────────────────────────────────
#  0301: Ausgabefähigkeit prüfen
# ─────────────────────────────────────────────


@router.get("/gegenstaende/{inventarnummer}/ausgabefaehigkeit")
def pruefe_ausgabefaehigkeit(
    inventarnummer: str,
    mitglied_id: uuid.UUID = Query(..., alias="mitglied_id"),
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> AusgabefaehigkeitAntwort:
    """GET /gegenstaende/{inventarnummer}/ausgabefaehigkeit — 0301"""
    _pruefe_rolle(x_role, _ROLLEN_LESEN)
    heute = ausleihe_app._datumsquelle.heute()
    try:
        result = prüfe_ausgabefaehigkeit(session, inventarnummer, mitglied_id, heute)
    except GegenstandNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "GEGENSTAND_NICHT_GEFUNDEN", "beschreibung": str(exc)},
        ) from exc
    except MitgliedNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "MITGLIED_NICHT_GEFUNDEN", "beschreibung": str(exc)},
        ) from exc
    return AusgabefaehigkeitAntwort(**result)


# ─────────────────────────────────────────────
#  0302: Ausleihe anlegen
# ─────────────────────────────────────────────


@router.post("/ausleihen", status_code=201)
def erstelle_ausleihe(
    anfrage: AusleiheAnlegen,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> AusleiheAnlegenAntwort:
    """POST /ausleihen — 0302"""
    _pruefe_rolle(x_role, _ROLLEN_THEKE)
    heute = ausleihe_app._datumsquelle.heute()
    try:
        mitglied_id = uuid.UUID(anfrage.mitgliedId)
    except ValueError:
        raise HTTPException(status_code=400, detail={"fehler_code": "EINGABE_UNGUELTIG", "beschreibung": "mitgliedId ist keine gültige UUID."})

    try:
        ausleihe = ausleihe_anlegen(
            session,
            inventarnummer=anfrage.gegenstandId,
            mitglied_id=mitglied_id,
            heute=heute,
            ausgabedatum=anfrage.ausgabedatum,
        )
    except MitgliedGesperrt:
        raise HTTPException(
            status_code=422,
            detail={"fehler_code": "MITGLIED_GESPERRT", "beschreibung": "Das Mitglied ist gesperrt."},
        )
    except AusleihlimitErreicht:
        raise HTTPException(
            status_code=422,
            detail={"fehler_code": "AUSLEIHLIMIT_ERREICHT", "beschreibung": "Ausleihlimit von 3 erreicht."},
        )
    except GegenstandWartungsfaellig:
        raise HTTPException(
            status_code=422,
            detail={"fehler_code": "GEGENSTAND_WARTUNGSFAELLIG", "beschreibung": "Gegenstand ist wartungsfällig."},
        )
    except GegenstandNichtVerfuegbar:
        raise HTTPException(
            status_code=422,
            detail={"fehler_code": "GEGENSTAND_NICHT_VERFUEGBAR", "beschreibung": "Gegenstand ist nicht verfügbar."},
        )
    except EinweisungFehlt:
        raise HTTPException(
            status_code=422,
            detail={"fehler_code": "EINWEISUNG_FEHLT", "beschreibung": "Einweisung fehlt."},
        )
    except (GegenstandNichtGefunden, MitgliedNichtGefunden) as exc:
        code = "GEGENSTAND_NICHT_GEFUNDEN" if isinstance(exc, GegenstandNichtGefunden) else "MITGLIED_NICHT_GEFUNDEN"
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": code, "beschreibung": str(exc)},
        ) from exc

    # Gegenstand für Inventarnummer und Leihdauer
    gegenstand = session.get(Gegenstand, ausleihe.gegenstand_id)
    from leihgut.domain.models import Kategorie
    kategorie = session.get(Kategorie, gegenstand.kategorie_id) if gegenstand else None
    inventarnummer = gegenstand.inventarnummer if gegenstand else anfrage.gegenstandId
    leihdauer = kategorie.leihdauer_tage if kategorie else 14

    return AusleiheAnlegenAntwort(
        ausleiheId=str(ausleihe.id),
        gegenstandId=inventarnummer,
        mitgliedId=str(ausleihe.mitglied_id),
        ausgabedatum=ausleihe.ausgabe_datum,
        rueckgabefrist=ausleihe.rueckgabefrist,
        kautionsbetrag=ausleihe.kaution_betrag,
        gegenstandZustand="ausgeliehen",
        leihdauerTage=leihdauer,
    )


# ─────────────────────────────────────────────
#  0304: Einzelne Ausleihe abfragen
# ─────────────────────────────────────────────


@router.get("/ausleihen/{ausleihe_id}")
def hole_ausleihe(
    ausleihe_id: uuid.UUID,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> AusleiheAntwort:
    """GET /ausleihen/{id} — 0304"""
    _pruefe_rolle(x_role, _ROLLEN_MITGLIED)
    heute = ausleihe_app._datumsquelle.heute()
    try:
        ausleihe = ausleihe_abfragen(session, ausleihe_id, heute)
    except AusleiheNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "AUSLEIHE_NICHT_GEFUNDEN", "beschreibung": str(exc)},
        ) from exc
    inventarnummer = _hole_inventarnummer(session, ausleihe)
    return _ausleihe_zu_antwort(ausleihe, inventarnummer, heute)


# ─────────────────────────────────────────────
#  0304: Ausleihen eines Mitglieds abfragen
# ─────────────────────────────────────────────


@router.get("/mitglieder/{mitglied_id}/ausleihen")
def liste_ausleihen_fuer_mitglied(
    mitglied_id: uuid.UUID,
    status: Optional[str] = Query(default=None),
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> list[AusleiheAntwort]:
    """GET /mitglieder/{id}/ausleihen — 0304"""
    _pruefe_rolle(x_role, _ROLLEN_LESEN)
    heute = ausleihe_app._datumsquelle.heute()
    try:
        ausleihen = ausleihen_abfragen_fuer_mitglied(session, mitglied_id, heute, status)
    except MitgliedNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "MITGLIED_NICHT_GEFUNDEN", "beschreibung": str(exc)},
        ) from exc
    result = []
    for a in ausleihen:
        inventarnummer = _hole_inventarnummer(session, a)
        result.append(_ausleihe_zu_antwort(a, inventarnummer, heute))
    return result


# ─────────────────────────────────────────────
#  0801/0802: Sperrstatus abfragen
# ─────────────────────────────────────────────


@router.get("/mitglieder/{mitglied_id}/sperrstatus")
def hole_sperrstatus(
    mitglied_id: uuid.UUID,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> SperrstatusAntwort:
    """GET /mitglieder/{id}/sperrstatus — 0801/0802"""
    _pruefe_rolle(x_role, _ROLLEN_LESEN)
    heute = ausleihe_app._datumsquelle.heute()
    try:
        result = sperrstatus_abfragen(session, mitglied_id, heute)
    except MitgliedNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "MITGLIED_NICHT_GEFUNDEN", "beschreibung": str(exc)},
        ) from exc
    return SperrstatusAntwort(**result)


# ─────────────────────────────────────────────
#  0303: Ausleihe verlängern
# ─────────────────────────────────────────────


@router.post("/ausleihen/{ausleihe_id}/verlaengerung")
def verlaengere_ausleihe(
    ausleihe_id: uuid.UUID,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> AusleiheAntwort:
    """POST /ausleihen/{id}/verlaengerung — 0303"""
    _pruefe_rolle(x_role, _ROLLEN_VERLAENGERN)
    heute = ausleihe_app._datumsquelle.heute()
    try:
        ausleihe = ausleihe_verlaengern(session, ausleihe_id, heute)
    except AusleiheNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "AUSLEIHE_NICHT_GEFUNDEN", "beschreibung": str(exc)},
        ) from exc
    except AusleiheNichtAktiv:
        raise HTTPException(
            status_code=409,
            detail={"fehler_code": "AUSLEIHE_NICHT_AKTIV", "beschreibung": "Ausleihe ist nicht aktiv."},
        )
    except BereitsVerlaengert:
        raise HTTPException(
            status_code=409,
            detail={"fehler_code": "BEREITS_VERLAENGERT", "beschreibung": "Ausleihe wurde bereits verlängert."},
        )
    except AusleiheUeberfaellig:
        raise HTTPException(
            status_code=409,
            detail={"fehler_code": "AUSLEIHE_UEBERFAELLIG", "beschreibung": "Ausleihe ist überfällig."},
        )
    except VormerkungOffen:
        raise HTTPException(
            status_code=409,
            detail={"fehler_code": "VORMERKUNG_OFFEN", "beschreibung": "Offene Vormerkung für diese Kategorie."},
        )
    inventarnummer = _hole_inventarnummer(session, ausleihe)
    # Verlängerung: nach Prüfung immer aktiv und nicht überfällig
    object.__setattr__(ausleihe, "ueberfaellig", False)
    return _ausleihe_zu_antwort(ausleihe, inventarnummer, heute)
