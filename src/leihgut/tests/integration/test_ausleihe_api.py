"""Integrationstests für EPIC-0300: Ausleihe + Verlängerung, EPIC-0800: Mitgliedersperre.

Nutzt das client-Fixture aus conftest.py (In-Memory SQLite, TestClient).
Issue: 0301, 0302, 0303, 0304, 0801, 0802
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlmodel import Session

from leihgut.application import ausleihe as ausleihe_app
from leihgut.domain.models import (
    Ausleihe,
    AusleiheStatus,
    Gegenstand,
    GegenstandZustand,
    Kategorie,
    Mitglied,
)
from leihgut.infrastructure.datum import FixesDatum

HEUTE = date(2026, 9, 1)


# ─────────────────────────────────────────────
#  Fixtures / Hilfsfunktionen
# ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def fixiere_datum():
    """Alle Tests laufen mit festem Datum 2026-09-01."""
    ausleihe_app.set_datumsquelle(FixesDatum(HEUTE))
    yield
    ausleihe_app.set_datumsquelle(ausleihe_app.SystemDatumsQuelle())


def _erstelle_kategorie(session: Session, name="Bohrmaschine", leihdauer=14, einweisung=False):
    k = Kategorie(
        name=name,
        leihdauer_tage=leihdauer,
        wartungsintervall_ausleihen=10,
        einweisungspflichtig=einweisung,
    )
    session.add(k)
    session.commit()
    session.refresh(k)
    return k


def _erstelle_gegenstand(session: Session, kategorie: Kategorie, inventarnummer="INV-001", wbw=200, zustand=GegenstandZustand.verfuegbar):
    g = Gegenstand(
        inventarnummer=inventarnummer,
        kategorie_id=kategorie.id,
        wiederbeschaffungswert_euro=wbw,
        zustand=zustand,
    )
    session.add(g)
    session.commit()
    session.refresh(g)
    return g


def _erstelle_mitglied(session: Session, name="Max Muster"):
    m = Mitglied(name=name)
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def _erstelle_ausleihe(session: Session, gegenstand: Gegenstand, mitglied: Mitglied, rueckgabefrist: date, status=AusleiheStatus.aktiv):
    a = Ausleihe(
        gegenstand_id=gegenstand.id,
        mitglied_id=mitglied.id,
        ausgabe_datum=HEUTE - timedelta(days=14),
        rueckgabefrist=rueckgabefrist,
        kaution_betrag=40,
        status=status,
    )
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


# ─────────────────────────────────────────────
#  0301: Ausgabefähigkeit prüfen
# ─────────────────────────────────────────────


def test_ausgabefaehigkeit_darf_ausgegeben(client, session):
    # 0301
    k = _erstelle_kategorie(session)
    g = _erstelle_gegenstand(session, k)
    m = _erstelle_mitglied(session)

    resp = client.get(
        f"/gegenstaende/{g.inventarnummer}/ausgabefaehigkeit",
        params={"mitglied_id": str(m.id)},
        headers={"X-Role": "thekendienst"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["darfAusgegeben"] is True
    assert body["ablehnungsgruende"] == []


def test_ausgabefaehigkeit_mitglied_gesperrt(client, session):
    # 0301, 0801
    k = _erstelle_kategorie(session)
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-002")
    m = _erstelle_mitglied(session)
    # Überfällige Ausleihe anlegen
    g2 = _erstelle_gegenstand(session, k, inventarnummer="INV-009")
    _erstelle_ausleihe(session, g2, m, rueckgabefrist=date(2026, 8, 1))  # überfällig

    resp = client.get(
        f"/gegenstaende/{g.inventarnummer}/ausgabefaehigkeit",
        params={"mitglied_id": str(m.id)},
        headers={"X-Role": "wart"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["darfAusgegeben"] is False
    assert any("BR-07" in gr for gr in body["ablehnungsgruende"])


def test_ausgabefaehigkeit_gegenstand_nicht_gefunden(client, session):
    # 0301
    m = _erstelle_mitglied(session)
    resp = client.get(
        "/gegenstaende/UNBEKANNT/ausgabefaehigkeit",
        params={"mitglied_id": str(m.id)},
        headers={"X-Role": "wart"},
    )
    assert resp.status_code == 404
    assert resp.json()["fehler_code"] == "GEGENSTAND_NICHT_GEFUNDEN"


def test_ausgabefaehigkeit_mitglied_nicht_gefunden(client, session):
    # 0301
    k = _erstelle_kategorie(session)
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-003")
    resp = client.get(
        f"/gegenstaende/{g.inventarnummer}/ausgabefaehigkeit",
        params={"mitglied_id": str(uuid.uuid4())},
        headers={"X-Role": "wart"},
    )
    assert resp.status_code == 404
    assert resp.json()["fehler_code"] == "MITGLIED_NICHT_GEFUNDEN"


def test_ausgabefaehigkeit_falsche_rolle(client, session):
    # 0301
    k = _erstelle_kategorie(session)
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-004")
    m = _erstelle_mitglied(session)
    resp = client.get(
        f"/gegenstaende/{g.inventarnummer}/ausgabefaehigkeit",
        params={"mitglied_id": str(m.id)},
        headers={"X-Role": "mitglied"},
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────
#  0302: Gegenstand ausleihen
# ─────────────────────────────────────────────


def test_ausleihe_anlegen_happy_path(client, session):
    # 0302
    k = _erstelle_kategorie(session, leihdauer=14)
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-010")
    m = _erstelle_mitglied(session)

    resp = client.post(
        "/ausleihen",
        json={
            "gegenstandId": g.inventarnummer,
            "mitgliedId": str(m.id),
            "ausgabedatum": "2026-09-01",
        },
        headers={"X-Role": "thekendienst"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["gegenstandId"] == g.inventarnummer
    assert body["rueckgabefrist"] == "2026-09-15"
    assert body["gegenstandZustand"] == "ausgeliehen"
    assert body["leihdauerTage"] == 14
    assert body["kautionsbetrag"] == 40  # 20% von 200

    # Gegenstand muss ausgeliehen sein
    session.refresh(g)
    assert g.zustand == GegenstandZustand.ausgeliehen


def test_ausleihe_anlegen_ohne_datum_nimmt_heute(client, session):
    # 0302
    k = _erstelle_kategorie(session, name="Kat2", leihdauer=7)
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-011")
    m = _erstelle_mitglied(session)

    resp = client.post(
        "/ausleihen",
        json={"gegenstandId": g.inventarnummer, "mitgliedId": str(m.id)},
        headers={"X-Role": "thekendienst"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["ausgabedatum"] == "2026-09-01"
    assert body["rueckgabefrist"] == "2026-09-08"


def test_ausleihe_anlegen_mitglied_gesperrt(client, session):
    # 0302, 0801
    k = _erstelle_kategorie(session, name="Kat3")
    g_alt = _erstelle_gegenstand(session, k, inventarnummer="INV-020")
    g_neu = _erstelle_gegenstand(session, k, inventarnummer="INV-021")
    m = _erstelle_mitglied(session)
    _erstelle_ausleihe(session, g_alt, m, rueckgabefrist=date(2026, 8, 1))

    resp = client.post(
        "/ausleihen",
        json={"gegenstandId": g_neu.inventarnummer, "mitgliedId": str(m.id)},
        headers={"X-Role": "thekendienst"},
    )
    assert resp.status_code == 422
    assert resp.json()["fehler_code"] == "MITGLIED_GESPERRT"


def test_ausleihe_anlegen_limit_erreicht(client, session):
    # 0302
    k = _erstelle_kategorie(session, name="Kat4")
    m = _erstelle_mitglied(session)
    # 3 aktive Ausleihen anlegen
    for i in range(3):
        gi = _erstelle_gegenstand(session, k, inventarnummer=f"INV-03{i}", zustand=GegenstandZustand.ausgeliehen)
        _erstelle_ausleihe(session, gi, m, rueckgabefrist=date(2026, 9, 30))
    g_neu = _erstelle_gegenstand(session, k, inventarnummer="INV-040")

    resp = client.post(
        "/ausleihen",
        json={"gegenstandId": g_neu.inventarnummer, "mitgliedId": str(m.id)},
        headers={"X-Role": "thekendienst"},
    )
    assert resp.status_code == 422
    assert resp.json()["fehler_code"] == "AUSLEIHLIMIT_ERREICHT"


def test_ausleihe_anlegen_gegenstand_nicht_verfuegbar(client, session):
    # 0302
    k = _erstelle_kategorie(session, name="Kat5")
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-050", zustand=GegenstandZustand.ausgeliehen)
    m = _erstelle_mitglied(session)

    resp = client.post(
        "/ausleihen",
        json={"gegenstandId": g.inventarnummer, "mitgliedId": str(m.id)},
        headers={"X-Role": "thekendienst"},
    )
    assert resp.status_code == 422
    assert resp.json()["fehler_code"] == "GEGENSTAND_NICHT_VERFUEGBAR"


def test_ausleihe_anlegen_einweisung_fehlt(client, session):
    # 0302
    k = _erstelle_kategorie(session, name="Kat6", einweisung=True)
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-060")
    m = _erstelle_mitglied(session)

    resp = client.post(
        "/ausleihen",
        json={"gegenstandId": g.inventarnummer, "mitgliedId": str(m.id)},
        headers={"X-Role": "thekendienst"},
    )
    assert resp.status_code == 422
    assert resp.json()["fehler_code"] == "EINWEISUNG_FEHLT"


def test_ausleihe_anlegen_wartungsfaellig(client, session):
    # 0302
    k = _erstelle_kategorie(session, name="Kat7")
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-070", zustand=GegenstandZustand.wartungsfaellig)
    m = _erstelle_mitglied(session)

    resp = client.post(
        "/ausleihen",
        json={"gegenstandId": g.inventarnummer, "mitgliedId": str(m.id)},
        headers={"X-Role": "thekendienst"},
    )
    assert resp.status_code == 422
    assert resp.json()["fehler_code"] == "GEGENSTAND_WARTUNGSFAELLIG"


def test_ausleihe_anlegen_falsche_rolle(client, session):
    # 0302
    k = _erstelle_kategorie(session, name="Kat8")
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-080")
    m = _erstelle_mitglied(session)

    resp = client.post(
        "/ausleihen",
        json={"gegenstandId": g.inventarnummer, "mitgliedId": str(m.id)},
        headers={"X-Role": "wart"},
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────
#  0304: Ausleihe abfragen
# ─────────────────────────────────────────────


def test_ausleihe_abfragen_happy_path(client, session):
    # 0304
    k = _erstelle_kategorie(session, name="Kat9")
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-090", zustand=GegenstandZustand.ausgeliehen)
    m = _erstelle_mitglied(session)
    a = _erstelle_ausleihe(session, g, m, rueckgabefrist=date(2026, 9, 30))

    resp = client.get(f"/ausleihen/{a.id}", headers={"X-Role": "thekendienst"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ausleiheId"] == str(a.id)
    assert body["ueberfaellig"] is False


def test_ausleihe_abfragen_ueberfaellig(client, session):
    # 0304, 0801
    k = _erstelle_kategorie(session, name="Kat10")
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-100", zustand=GegenstandZustand.ausgeliehen)
    m = _erstelle_mitglied(session)
    a = _erstelle_ausleihe(session, g, m, rueckgabefrist=date(2026, 8, 1))

    resp = client.get(f"/ausleihen/{a.id}", headers={"X-Role": "wart"})
    assert resp.status_code == 200
    assert resp.json()["ueberfaellig"] is True


def test_ausleihe_abfragen_nicht_gefunden(client, session):
    # 0304
    resp = client.get(f"/ausleihen/{uuid.uuid4()}", headers={"X-Role": "wart"})
    assert resp.status_code == 404
    assert resp.json()["fehler_code"] == "AUSLEIHE_NICHT_GEFUNDEN"


def test_mitglied_ausleihen_abfragen(client, session):
    # 0304
    k = _erstelle_kategorie(session, name="Kat11")
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-110", zustand=GegenstandZustand.ausgeliehen)
    m = _erstelle_mitglied(session)
    _erstelle_ausleihe(session, g, m, rueckgabefrist=date(2026, 9, 30))

    resp = client.get(f"/mitglieder/{m.id}/ausleihen", headers={"X-Role": "thekendienst"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_mitglied_ausleihen_status_filter(client, session):
    # 0304
    k = _erstelle_kategorie(session, name="Kat12")
    g1 = _erstelle_gegenstand(session, k, inventarnummer="INV-120", zustand=GegenstandZustand.ausgeliehen)
    g2 = _erstelle_gegenstand(session, k, inventarnummer="INV-121", zustand=GegenstandZustand.ausgeliehen)
    m = _erstelle_mitglied(session)
    _erstelle_ausleihe(session, g1, m, rueckgabefrist=date(2026, 9, 30))
    _erstelle_ausleihe(session, g2, m, rueckgabefrist=date(2026, 8, 1), status=AusleiheStatus.abgeschlossen)

    resp = client.get(f"/mitglieder/{m.id}/ausleihen?status=aktiv", headers={"X-Role": "wart"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "aktiv"


# ─────────────────────────────────────────────
#  0801/0802: Sperrstatus
# ─────────────────────────────────────────────


def test_sperrstatus_nicht_gesperrt(client, session):
    # 0801
    m = _erstelle_mitglied(session)
    resp = client.get(f"/mitglieder/{m.id}/sperrstatus", headers={"X-Role": "thekendienst"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["gesperrt"] is False
    assert body["ueberfaelligeAusleihen"] == 0


def test_sperrstatus_gesperrt(client, session):
    # 0801
    k = _erstelle_kategorie(session, name="Kat13")
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-130", zustand=GegenstandZustand.ausgeliehen)
    m = _erstelle_mitglied(session)
    _erstelle_ausleihe(session, g, m, rueckgabefrist=date(2026, 8, 1))

    resp = client.get(f"/mitglieder/{m.id}/sperrstatus", headers={"X-Role": "wart"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["gesperrt"] is True
    assert body["ueberfaelligeAusleihen"] == 1


def test_sperrstatus_aufgehoben_nach_abschluss(client, session):
    # 0802
    k = _erstelle_kategorie(session, name="Kat14")
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-140", zustand=GegenstandZustand.ausgeliehen)
    m = _erstelle_mitglied(session)
    a = _erstelle_ausleihe(session, g, m, rueckgabefrist=date(2026, 8, 1))
    a.status = AusleiheStatus.abgeschlossen
    session.add(a)
    session.commit()

    resp = client.get(f"/mitglieder/{m.id}/sperrstatus", headers={"X-Role": "wart"})
    assert resp.status_code == 200
    assert resp.json()["gesperrt"] is False


def test_sperrstatus_mitglied_nicht_gefunden(client, session):
    # 0801
    resp = client.get(f"/mitglieder/{uuid.uuid4()}/sperrstatus", headers={"X-Role": "wart"})
    assert resp.status_code == 404
    assert resp.json()["fehler_code"] == "MITGLIED_NICHT_GEFUNDEN"


# ─────────────────────────────────────────────
#  0303: Ausleihe verlängern
# ─────────────────────────────────────────────


def test_verlaengerung_happy_path(client, session):
    # 0303
    k = _erstelle_kategorie(session, name="Kat15", leihdauer=14)
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-150", zustand=GegenstandZustand.ausgeliehen)
    m = _erstelle_mitglied(session)
    a = _erstelle_ausleihe(session, g, m, rueckgabefrist=date(2026, 9, 15))

    resp = client.post(f"/ausleihen/{a.id}/verlaengerung", headers={"X-Role": "thekendienst"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verlaengert"] is True
    assert body["rueckgabefrist"] == "2026-09-29"  # 9-15 + 14 Tage


def test_verlaengerung_bereits_verlaengert(client, session):
    # 0303
    k = _erstelle_kategorie(session, name="Kat16", leihdauer=14)
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-160", zustand=GegenstandZustand.ausgeliehen)
    m = _erstelle_mitglied(session)
    a = _erstelle_ausleihe(session, g, m, rueckgabefrist=date(2026, 9, 15))
    a.verlaengert = True
    session.add(a)
    session.commit()

    resp = client.post(f"/ausleihen/{a.id}/verlaengerung", headers={"X-Role": "thekendienst"})
    assert resp.status_code == 409
    assert resp.json()["fehler_code"] == "BEREITS_VERLAENGERT"


def test_verlaengerung_ueberfaellig(client, session):
    # 0303
    k = _erstelle_kategorie(session, name="Kat17", leihdauer=14)
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-170", zustand=GegenstandZustand.ausgeliehen)
    m = _erstelle_mitglied(session)
    a = _erstelle_ausleihe(session, g, m, rueckgabefrist=date(2026, 8, 1))

    resp = client.post(f"/ausleihen/{a.id}/verlaengerung", headers={"X-Role": "mitglied"})
    assert resp.status_code == 409
    assert resp.json()["fehler_code"] == "AUSLEIHE_UEBERFAELLIG"


def test_verlaengerung_nicht_aktiv(client, session):
    # 0303
    k = _erstelle_kategorie(session, name="Kat18", leihdauer=14)
    g = _erstelle_gegenstand(session, k, inventarnummer="INV-180", zustand=GegenstandZustand.ausgeliehen)
    m = _erstelle_mitglied(session)
    a = _erstelle_ausleihe(session, g, m, rueckgabefrist=date(2026, 9, 15), status=AusleiheStatus.abgeschlossen)

    resp = client.post(f"/ausleihen/{a.id}/verlaengerung", headers={"X-Role": "thekendienst"})
    assert resp.status_code == 409
    assert resp.json()["fehler_code"] == "AUSLEIHE_NICHT_AKTIV"


def test_verlaengerung_nicht_gefunden(client, session):
    # 0303
    resp = client.post(f"/ausleihen/{uuid.uuid4()}/verlaengerung", headers={"X-Role": "thekendienst"})
    assert resp.status_code == 404
    assert resp.json()["fehler_code"] == "AUSLEIHE_NICHT_GEFUNDEN"
