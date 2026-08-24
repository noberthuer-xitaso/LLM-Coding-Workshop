"""API-Router für EPIC-0400: Rückgabe & Prüfung, EPIC-0500: Kaution.

Issue: # 0401, # 0402, # 0403, # 0502, # 0503, # 0504
HTTP-Routing, Serialisierung und Rollenkontrolle gemäß Interface Contract.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from sqlmodel import Session

from leihgut.api.schemas.pruefprotokoll import (
    KautionsbewegungAntwort,
    PruefprotokollAnfrage,
    PruefprotokollAntwort,
    RueckgabeAnfrage,
    RueckgabeAntwort,
)
from leihgut.application import pruefprotokoll as pp_app
from leihgut.application.pruefprotokoll import (
    AusleiheNichtAktiv,
    AusleiheNichtGefunden,
    AusleiheNichtInPruefung,
    GegenstandNichtAusgeliehen,
    KautionsabzugZuHoch,
    MitgliedNichtGefunden,
    PruefprotokollBereitsVorhanden,
)
from leihgut.domain.models import Gegenstand, KautionsbewegungArt
from leihgut.infrastructure.datenbank import get_session

router = APIRouter()

_ROLLEN_WART = {"wart"}
_ROLLEN_THEKE = {"thekendienst"}
_ROLLEN_LESEN = {"wart", "thekendienst"}


def _pruefe_rolle(rolle: str, erlaubte: set[str]) -> None:
    if rolle not in erlaubte:
        raise HTTPException(
            status_code=403,
            detail={
                "fehler_code": "ROLLE_NICHT_BERECHTIGT",
                "beschreibung": f"Rolle '{rolle}' hat keine Berechtigung.",
            },
        )


def _protokoll_zu_antwort(protokoll, inventarnummer: str) -> PruefprotokollAntwort:
    reserviert_fuer = getattr(protokoll, "reserviert_fuer", None)
    vorheriges_id = getattr(protokoll, "vorheriges_pruefprotokoll_id", None)
    nachzustand_eingabe = getattr(protokoll, "nachzustand_eingabe", protokoll.nachzustand)
    return PruefprotokollAntwort(
        pruefprotokollId=str(protokoll.id),
        ausleiheId=str(protokoll.ausleihe_id),
        gegenstandId=inventarnummer,
        wartId=protokoll.wart_id,
        zeitstempel=protokoll.erstellt_am,
        nachzustandEingabe=nachzustand_eingabe.value
        if hasattr(nachzustand_eingabe, "value")
        else str(nachzustand_eingabe),
        nachzustandEffektiv=getattr(protokoll, "nachzustand_effektiv", ""),
        kautionsabzug=protokoll.kautionsabzug,
        kautionFreigegeben=getattr(protokoll, "kaution_freigegeben", 0),
        begruendung=protokoll.begruendung,
        reserviertFuer=str(reserviert_fuer) if reserviert_fuer else None,
        vorherigePruefprotokoll=str(vorheriges_id) if vorheriges_id else None,
    )


# ─────────────────────────────────────────────
#  0401: Gegenstand zurücknehmen
# ─────────────────────────────────────────────


@router.post("/ausleihen/{ausleihe_id}/rueckgabe")
def erfasse_rueckgabe(
    ausleihe_id: uuid.UUID,
    anfrage: Optional[RueckgabeAnfrage] = Body(default=None),
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> RueckgabeAntwort:
    """POST /ausleihen/{id}/rueckgabe — 0401"""
    _pruefe_rolle(x_role, _ROLLEN_THEKE)
    heute = pp_app._datumsquelle.heute()
    auffaelligkeiten = anfrage.auffaelligkeiten if anfrage else None

    try:
        ausleihe = pp_app.rueckgabe_erfassen(session, ausleihe_id, heute, auffaelligkeiten)
    except AusleiheNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "AUSLEIHE_NICHT_GEFUNDEN", "beschreibung": str(exc.ausleihe_id)},
        ) from exc
    except GegenstandNichtAusgeliehen:
        raise HTTPException(
            status_code=409,
            detail={
                "fehler_code": "GEGENSTAND_NICHT_AUSGELIEHEN",
                "beschreibung": "Gegenstand ist nicht ausgeliehen.",
            },
        )

    gegenstand = session.get(Gegenstand, ausleihe.gegenstand_id)
    inventarnummer = gegenstand.inventarnummer if gegenstand else str(ausleihe.gegenstand_id)
    zustand = gegenstand.zustand.value if gegenstand else "in_Prüfung"

    return RueckgabeAntwort(
        ausleiheId=str(ausleihe.id),
        gegenstandId=inventarnummer,
        zustand=zustand,
        zeitstempelRueckgabe=datetime.now(),
    )


# ─────────────────────────────────────────────
#  0402: Prüfprotokoll erstellen
# ─────────────────────────────────────────────


@router.post("/ausleihen/{ausleihe_id}/pruefprotokoll", status_code=201)
def erstelle_pruefprotokoll(
    ausleihe_id: uuid.UUID,
    anfrage: PruefprotokollAnfrage,
    x_role: str = Header(default=""),
    x_user: str = Header(default="wart"),
    session: Session = Depends(get_session),
) -> PruefprotokollAntwort:
    """POST /ausleihen/{id}/pruefprotokoll — 0402"""
    _pruefe_rolle(x_role, _ROLLEN_WART)
    heute = pp_app._datumsquelle.heute()

    try:
        protokoll = pp_app.pruefprotokoll_erstellen(
            session,
            ausleihe_id,
            x_user,
            anfrage.nachzustand,
            anfrage.kautionsabzug,
            anfrage.begruendung,
            heute,
        )
    except AusleiheNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "AUSLEIHE_NICHT_GEFUNDEN", "beschreibung": str(exc.ausleihe_id)},
        ) from exc
    except AusleiheNichtInPruefung:
        raise HTTPException(
            status_code=409,
            detail={
                "fehler_code": "GEGENSTAND_NICHT_IN_PRUEFUNG",
                "beschreibung": "Ausleihe ist nicht im Status 'in_Prüfung'.",
            },
        )
    except PruefprotokollBereitsVorhanden:
        raise HTTPException(
            status_code=409,
            detail={
                "fehler_code": "PRUEFPROTOKOLL_BEREITS_VORHANDEN",
                "beschreibung": "Für diese Ausleihe existiert bereits ein Prüfprotokoll.",
            },
        )
    except KautionsabzugZuHoch:
        raise HTTPException(
            status_code=422,
            detail={
                "fehler_code": "KAUTIONSABZUG_ZU_HOCH",
                "beschreibung": "Kautionsabzug übersteigt die hinterlegte Kaution (BR-21).",
            },
        )

    inventarnummer = getattr(protokoll, "gegenstand_inventarnummer", "")
    return _protokoll_zu_antwort(protokoll, inventarnummer)


# ─────────────────────────────────────────────
#  0403: Gegenstand als verloren erklären
# ─────────────────────────────────────────────


@router.post("/ausleihen/{ausleihe_id}/verloren", status_code=201)
def erklaere_verloren(
    ausleihe_id: uuid.UUID,
    x_role: str = Header(default=""),
    x_user: str = Header(default="wart"),
    session: Session = Depends(get_session),
) -> PruefprotokollAntwort:
    """POST /ausleihen/{id}/verloren — 0403"""
    _pruefe_rolle(x_role, _ROLLEN_WART)
    heute = pp_app._datumsquelle.heute()

    try:
        protokoll = pp_app.verloren_erklaeren(session, ausleihe_id, x_user, heute)
    except AusleiheNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "AUSLEIHE_NICHT_GEFUNDEN", "beschreibung": str(exc.ausleihe_id)},
        ) from exc
    except AusleiheNichtAktiv:
        raise HTTPException(
            status_code=409,
            detail={
                "fehler_code": "AUSLEIHE_NICHT_AKTIV",
                "beschreibung": "Ausleihe ist nicht aktiv.",
            },
        )
    except PruefprotokollBereitsVorhanden:
        raise HTTPException(
            status_code=409,
            detail={
                "fehler_code": "PRUEFPROTOKOLL_BEREITS_VORHANDEN",
                "beschreibung": "Für diese Ausleihe existiert bereits ein Prüfprotokoll.",
            },
        )

    inventarnummer = getattr(protokoll, "gegenstand_inventarnummer", "")
    return _protokoll_zu_antwort(protokoll, inventarnummer)


# ─────────────────────────────────────────────
#  0504: Kautionsbewegungen abfragen
# ─────────────────────────────────────────────


@router.get("/mitglieder/{mitglied_id}/kautionsbewegungen")
def liste_kautionsbewegungen(
    mitglied_id: uuid.UUID,
    ausleihe_id: Optional[uuid.UUID] = Query(default=None),
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> list[KautionsbewegungAntwort]:
    """GET /mitglieder/{id}/kautionsbewegungen — 0504"""
    _pruefe_rolle(x_role, _ROLLEN_LESEN)

    try:
        bewegungen = pp_app.kautionsbewegungen_abfragen(session, mitglied_id, ausleihe_id)
    except MitgliedNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={"fehler_code": "MITGLIED_NICHT_GEFUNDEN", "beschreibung": str(exc.mitglied_id)},
        ) from exc

    return [
        KautionsbewegungAntwort(
            id=str(b.id),
            art=b.art.value,
            betrag=b.betrag,
            zeitstempel=b.zeitstempel,
            ausleiheId=str(b.ausleihe_id),
            pruefprotokollId=(
                str(b.referenz_id)
                if b.referenz_id and b.art != KautionsbewegungArt.hinterlegung
                else None
            ),
        )
        for b in bewegungen
    ]
