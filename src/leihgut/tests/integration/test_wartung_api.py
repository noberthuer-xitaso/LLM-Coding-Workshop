"""Integrationstests für EPIC-0600: Wartung und Ausmusterung.

Issue: # 0603, # 0604
Nutzt das client-Fixture aus conftest.py (In-Memory SQLite, TestClient).
"""

import uuid
from datetime import date, datetime

import pytest
from sqlmodel import Session

from leihgut.application import wartung as wartung_app
from leihgut.domain.models import (
    Gegenstand,
    GegenstandZustand,
    Kategorie,
    Mitglied,
    Vormerkung,
    VormerkungStatus,
)
from leihgut.infrastructure.datum import FixesDatum

HEUTE = date(2026, 9, 1)
HEADERS_WART = {"x-role": "wart"}


# ─────────────────────────────────────────────
#  Fixtures: Datum fixieren
# ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def fixiere_datum():
    """Alle Tests laufen mit festem Datum 2026-09-01."""
    festes = FixesDatum(HEUTE)
    wartung_app.set_datumsquelle(festes)
    yield
    wartung_app.set_datumsquelle(wartung_app.SystemDatumsQuelle())


# ─────────────────────────────────────────────
#  Hilfsfunktionen
# ─────────────────────────────────────────────


def _kategorie(session: Session, *, name="Bohrmaschine", intervall=10) -> Kategorie:
    k = Kategorie(name=name, leihdauer_tage=14, wartungsintervall_ausleihen=intervall)
    session.add(k)
    session.commit()
    session.refresh(k)
    return k


def _gegenstand(
    session: Session,
    kategorie: Kategorie,
    *,
    inventarnummer="INV-W001",
    zustand=GegenstandZustand.wartungsfaellig,
    nutzungszaehler=10,
) -> Gegenstand:
    g = Gegenstand(
        inventarnummer=inventarnummer,
        kategorie_id=kategorie.id,
        wiederbeschaffungswert_euro=200,
        zustand=zustand,
        nutzungszaehler=nutzungszaehler,
    )
    session.add(g)
    session.commit()
    session.refresh(g)
    return g


def _mitglied(session: Session, name="Wart-Tester") -> Mitglied:
    m = Mitglied(name=name)
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def _vormerkung(session: Session, mitglied: Mitglied, kategorie: Kategorie) -> Vormerkung:
    v = Vormerkung(
        mitglied_id=mitglied.id,
        kategorie_id=kategorie.id,
        eingangszeit=datetime(2026, 8, 1, 10, 0, 0),
        status=VormerkungStatus.aktiv,
    )
    session.add(v)
    session.commit()
    session.refresh(v)
    return v


# ─────────────────────────────────────────────
#  Story 0603: Wartung abschließen
# ─────────────────────────────────────────────


def test_wartung_abschliessen_happy_path(client, session):
    """# 0603 — wartungsfälliger Gegenstand → verfügbar, Zähler = 0."""
    k = _kategorie(session)
    _gegenstand(session, k)

    resp = client.post("/gegenstaende/INV-W001/wartung-abschliessen", headers=HEADERS_WART)

    assert resp.status_code == 200
    body = resp.json()
    assert body["inventarnummer"] == "INV-W001"
    assert body["zustand"] == "verfügbar"
    assert body["nutzungszaehler"] == 0
    assert body["reserviertFuer"] is None


def test_wartung_abschliessen_mit_offener_vormerkung(client, session):
    """# 0603 — wartungsfälliger Gegenstand + Vormerkung → reserviert."""
    k = _kategorie(session)
    _gegenstand(session, k)
    m = _mitglied(session)
    _vormerkung(session, m, k)

    resp = client.post("/gegenstaende/INV-W001/wartung-abschliessen", headers=HEADERS_WART)

    assert resp.status_code == 200
    body = resp.json()
    assert body["zustand"] == "reserviert"
    assert body["nutzungszaehler"] == 0
    assert body["reserviertFuer"] == str(m.id)


def test_wartung_abschliessen_gegenstand_nicht_gefunden(client, session):
    """# 0603 — unbekannte Inventarnummer → 404 GEGENSTAND_NICHT_GEFUNDEN."""
    resp = client.post("/gegenstaende/INV-UNBEKANNT/wartung-abschliessen", headers=HEADERS_WART)

    assert resp.status_code == 404
    assert resp.json()["fehler_code"] == "GEGENSTAND_NICHT_GEFUNDEN"


def test_wartung_abschliessen_nicht_wartungsfaellig(client, session):
    """# 0603 — verfügbarer Gegenstand → 422 GEGENSTAND_NICHT_WARTUNGSFAELLIG."""
    k = _kategorie(session)
    _gegenstand(session, k, zustand=GegenstandZustand.verfuegbar, nutzungszaehler=3)

    resp = client.post("/gegenstaende/INV-W001/wartung-abschliessen", headers=HEADERS_WART)

    assert resp.status_code == 422
    assert resp.json()["fehler_code"] == "GEGENSTAND_NICHT_WARTUNGSFAELLIG"


def test_wartung_abschliessen_falsche_rolle(client, session):
    """# 0603 — falsche Rolle → 403 ROLLE_UNZULAESSIG."""
    k = _kategorie(session)
    _gegenstand(session, k)

    resp = client.post(
        "/gegenstaende/INV-W001/wartung-abschliessen",
        headers={"x-role": "thekendienst"},
    )

    assert resp.status_code == 403
    assert resp.json()["fehler_code"] == "ROLLE_UNZULAESSIG"


# ─────────────────────────────────────────────
#  Story 0604: Wartungsfällige Gegenstände abfragen
# ─────────────────────────────────────────────


def test_filter_wartungsfaellig_liefert_nur_wartungsfaellige(client, session):
    """# 0604 — GET /gegenstaende?zustand=wartungsfällig liefert nur wartungsfällige."""
    k = _kategorie(session)
    _gegenstand(session, k, inventarnummer="INV-W-WART", zustand=GegenstandZustand.wartungsfaellig)
    _gegenstand(session, k, inventarnummer="INV-W-VERF", zustand=GegenstandZustand.verfuegbar, nutzungszaehler=0)

    resp = client.get(
        "/gegenstaende",
        params={"zustand": "wartungsfällig"},
        headers={"x-role": "wart"},
    )

    assert resp.status_code == 200
    nummern = [g["inventarnummer"] for g in resp.json()]
    assert "INV-W-WART" in nummern
    assert "INV-W-VERF" not in nummern
