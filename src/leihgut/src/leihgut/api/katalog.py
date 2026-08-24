"""API-Router für EPIC-0100: Katalog verwalten.

HTTP-Routing, Serialisierung und Rollenkontrolle gemäß Interface Contract.
Rollenprüfung vor jedem Zugriff; Fehler im Einheitsformat.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlmodel import Session

from leihgut.api.schemas.katalog import (
    GegenstandAktualisierenAnfrage,
    GegenstandAnlegenAnfrage,
    GegenstandAntwort,
    KategorieAnlegenAnfrage,
    KategorieAntwort,
)
from leihgut.application.katalog import (
    GegenstandNichtGefunden,
    InventarnummerDoppelt,
    KategorieNameDoppelt,
    KategorieNichtGefunden,
    abfragen_gegenstand,
    abfragen_gegenstaende,
    abfragen_kategorie,
    abfragen_kategorien,
    aktualisieren_gegenstand,
    aktualisieren_kategorie,
    anlegen_gegenstand,
    anlegen_kategorie,
)
from leihgut.domain.models import GegenstandZustand
from leihgut.domain.regeln import berechne_kaution
from leihgut.infrastructure.datenbank import get_session

router = APIRouter()

_ROLLEN_SCHREIBEN = {"wart"}
_ROLLEN_LESEN = {"wart", "thekendienst"}


def _pruefe_schreiben(rolle: str) -> None:
    if rolle not in _ROLLEN_SCHREIBEN:
        raise HTTPException(
            status_code=403,
            detail={
                "fehler_code": "ROLLE_UNZULAESSIG",
                "beschreibung": f"Rolle '{rolle}' hat keine Schreibberechtigung.",
                "kontext": {"rolle": rolle},
            },
        )


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


def _kategorie_zu_antwort(k) -> KategorieAntwort:
    return KategorieAntwort(
        kategorieId=str(k.id),
        name=k.name,
        leihdauerTage=k.leihdauer_tage,
        wartungsintervallAusleihen=k.wartungsintervall_ausleihen,
        einweisungspflichtig=k.einweisungspflichtig,
    )


def _gegenstand_zu_antwort(g, k) -> GegenstandAntwort:
    return GegenstandAntwort(
        gegenstandId=str(g.id),
        inventarnummer=g.inventarnummer,
        kategorieId=str(g.kategorie_id),
        kategorieName=k.name,
        wiederbeschaffungswert=g.wiederbeschaffungswert_euro,
        kaution=berechne_kaution(g.wiederbeschaffungswert_euro),
        zustand=g.zustand.value,
        nutzungszaehler=g.nutzungszaehler,
    )


# ─────────────────────────────────────────────
#  Kategorie-Endpunkte
# ─────────────────────────────────────────────


@router.post("/kategorien", status_code=201)
def erstelle_kategorie(
    anfrage: KategorieAnlegenAnfrage,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> KategorieAntwort:
    """POST /kategorien — Neue Kategorie anlegen. Rolle: wart. (0101)"""
    _pruefe_schreiben(x_role)
    try:
        kategorie = anlegen_kategorie(
            session,
            name=anfrage.name,
            leihdauer_tage=anfrage.leihdauer_tage,
            wartungsintervall_ausleihen=anfrage.wartungsintervall_ausleihen,
            einweisungspflichtig=anfrage.einweisungspflichtig,
        )
    except KategorieNameDoppelt as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "fehler_code": "KATEGORIE_NAME_DOPPELT",
                "beschreibung": f"Kategorie '{exc.name}' existiert bereits.",
                "kontext": {"name": exc.name},
            },
        ) from exc
    return _kategorie_zu_antwort(kategorie)


@router.get("/kategorien")
def liste_kategorien(
    einweisungspflichtig: Optional[bool] = Query(default=None),
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> list[KategorieAntwort]:
    """GET /kategorien — Kategorien abfragen. Rollen: wart, thekendienst. (0104)"""
    _pruefe_lesen(x_role)
    kategorien = abfragen_kategorien(session, einweisungspflichtig=einweisungspflichtig)
    return [_kategorie_zu_antwort(k) for k in kategorien]


@router.get("/kategorien/{kategorie_id}")
def hole_kategorie(
    kategorie_id: uuid.UUID,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> KategorieAntwort:
    """GET /kategorien/{id} — Einzelne Kategorie abrufen. Rollen: wart, thekendienst. (0104)"""
    _pruefe_lesen(x_role)
    try:
        kategorie = abfragen_kategorie(session, kategorie_id)
    except KategorieNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "fehler_code": "KATEGORIE_NICHT_GEFUNDEN",
                "beschreibung": f"Kategorie '{exc.kategorie_id}' nicht gefunden.",
                "kontext": {"kategorieId": exc.kategorie_id},
            },
        ) from exc
    return _kategorie_zu_antwort(kategorie)


@router.put("/kategorien/{kategorie_id}")
def aktualisiere_kategorie(
    kategorie_id: uuid.UUID,
    anfrage: KategorieAnlegenAnfrage,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> KategorieAntwort:
    """PUT /kategorien/{id} — Kategorie vollständig aktualisieren. Rolle: wart. (0103)"""
    _pruefe_schreiben(x_role)
    try:
        kategorie = aktualisieren_kategorie(
            session,
            kategorie_id=kategorie_id,
            name=anfrage.name,
            leihdauer_tage=anfrage.leihdauer_tage,
            wartungsintervall_ausleihen=anfrage.wartungsintervall_ausleihen,
            einweisungspflichtig=anfrage.einweisungspflichtig,
        )
    except KategorieNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "fehler_code": "KATEGORIE_NICHT_GEFUNDEN",
                "beschreibung": f"Kategorie '{exc.kategorie_id}' nicht gefunden.",
                "kontext": {"kategorieId": exc.kategorie_id},
            },
        ) from exc
    except KategorieNameDoppelt as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "fehler_code": "KATEGORIE_NAME_DOPPELT",
                "beschreibung": f"Kategorie '{exc.name}' existiert bereits.",
                "kontext": {"name": exc.name},
            },
        ) from exc
    return _kategorie_zu_antwort(kategorie)


# ─────────────────────────────────────────────
#  Gegenstand-Endpunkte
# ─────────────────────────────────────────────


@router.post("/gegenstaende", status_code=201)
def erstelle_gegenstand(
    anfrage: GegenstandAnlegenAnfrage,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> GegenstandAntwort:
    """POST /gegenstaende — Neuen Gegenstand anlegen. Rolle: wart. (0102)"""
    _pruefe_schreiben(x_role)
    try:
        gegenstand, kategorie = anlegen_gegenstand(
            session,
            inventarnummer=anfrage.inventarnummer,
            kategorie_id=anfrage.kategorie_id,
            wiederbeschaffungswert=anfrage.wiederbeschaffungswert,
        )
    except InventarnummerDoppelt as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "fehler_code": "INVENTARNUMMER_DOPPELT",
                "beschreibung": f"Inventarnummer '{exc.inventarnummer}' existiert bereits.",
                "kontext": {"inventarnummer": exc.inventarnummer},
            },
        ) from exc
    except KategorieNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "fehler_code": "KATEGORIE_NICHT_GEFUNDEN",
                "beschreibung": f"Kategorie '{exc.kategorie_id}' nicht gefunden.",
                "kontext": {"kategorieId": exc.kategorie_id},
            },
        ) from exc
    return _gegenstand_zu_antwort(gegenstand, kategorie)


@router.get("/gegenstaende")
def liste_gegenstaende(
    kategorie_id: Optional[uuid.UUID] = Query(default=None, alias="kategorieId"),
    zustand: Optional[GegenstandZustand] = Query(default=None),
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> list[GegenstandAntwort]:
    """GET /gegenstaende — Gegenstände abfragen. Rollen: wart, thekendienst. (0104)"""
    _pruefe_lesen(x_role)
    paare = abfragen_gegenstaende(session, kategorie_id=kategorie_id, zustand=zustand)
    return [_gegenstand_zu_antwort(g, k) for g, k in paare]


@router.get("/gegenstaende/{inventarnummer}")
def hole_gegenstand(
    inventarnummer: str,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> GegenstandAntwort:
    """GET /gegenstaende/{inventarnummer} — Einzelnen Gegenstand abrufen. (0104)"""
    _pruefe_lesen(x_role)
    try:
        gegenstand, kategorie = abfragen_gegenstand(session, inventarnummer)
    except GegenstandNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "fehler_code": "GEGENSTAND_NICHT_GEFUNDEN",
                "beschreibung": f"Gegenstand '{exc.inventarnummer}' nicht gefunden.",
                "kontext": {"inventarnummer": exc.inventarnummer},
            },
        ) from exc
    return _gegenstand_zu_antwort(gegenstand, kategorie)


@router.patch("/gegenstaende/{inventarnummer}")
def patche_gegenstand(
    inventarnummer: str,
    anfrage: GegenstandAktualisierenAnfrage,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> GegenstandAntwort:
    """PATCH /gegenstaende/{inventarnummer} — Wiederbeschaffungswert ändern. Rolle: wart. (0103)"""
    _pruefe_schreiben(x_role)
    try:
        gegenstand, kategorie = aktualisieren_gegenstand(
            session,
            inventarnummer=inventarnummer,
            wiederbeschaffungswert=anfrage.wiederbeschaffungswert,
        )
    except GegenstandNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "fehler_code": "GEGENSTAND_NICHT_GEFUNDEN",
                "beschreibung": f"Gegenstand '{exc.inventarnummer}' nicht gefunden.",
                "kontext": {"inventarnummer": exc.inventarnummer},
            },
        ) from exc
    return _gegenstand_zu_antwort(gegenstand, kategorie)
