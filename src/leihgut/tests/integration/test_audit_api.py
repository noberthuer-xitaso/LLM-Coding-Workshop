"""Integrations-Tests für EPIC-0900: Audit-Log API.

Testet GET /audit und GET /audit/{id} über den HTTP-Client.
Prüft Rollenkontrolle, Filterung, Fehlerformate und 405 bei Schreibversuchen.
"""

# 0903

import uuid
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from leihgut.domain.models import (
    Ausleihe,
    AusleiheStatus,
    Gegenstand,
    Kategorie,
    Mitglied,
)
from leihgut.application.audit import erfasse_kautionsbewegung
from leihgut.domain.models import KautionsbewegungArt

_JETZT = datetime(2026, 8, 24, 10, 30, 0)


# ─────────────────────────────────────────────
#  Hilfsfunktionen
# ─────────────────────────────────────────────


def _erstelle_testdaten(session: Session):
    k = Kategorie(
        name="Bohrmaschinen",
        leihdauer_tage=7,
        wartungsintervall_ausleihen=10,
        einweisungspflichtig=False,
    )
    session.add(k)
    session.commit()
    session.refresh(k)

    g = Gegenstand(
        inventarnummer="BH-042",
        kategorie_id=k.id,
        wiederbeschaffungswert_euro=100,
    )
    session.add(g)
    session.commit()
    session.refresh(g)

    m = Mitglied(name="Testmitglied")
    session.add(m)
    session.commit()
    session.refresh(m)

    a = Ausleihe(
        gegenstand_id=g.id,
        mitglied_id=m.id,
        ausgabe_datum=date(2026, 8, 24),
        rueckgabefrist=date(2026, 8, 31),
        kaution_betrag=20,
        status=AusleiheStatus.aktiv,
    )
    session.add(a)
    session.commit()
    session.refresh(a)

    return k, g, m, a


# ─────────────────────────────────────────────
#  GET /audit — Grundfunktion
# ─────────────────────────────────────────────


def test_get_audit_leer(client: TestClient):
    """0903 — Leere Datenbank liefert leere Liste."""
    resp = client.get("/audit", headers={"x-role": "wart"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["eintraege"] == []
    assert body["total"] == 0


def test_get_audit_ein_eintrag(client: TestClient, session: Session):
    """0903 — Ein Eintrag wird korrekt serialisiert."""
    _, g, m, a = _erstelle_testdaten(session)
    erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.hinterlegung, 20, _JETZT)

    resp = client.get("/audit", headers={"x-role": "wart"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    e = body["eintraege"][0]
    assert e["art"] == "hinterlegung"
    assert e["betrag_euro"] == 20
    assert e["gegenstand_inventarnummer"] == "BH-042"
    assert e["mitglied_id"] == str(m.id)
    assert e["pruefprotokoll_id"] is None
    assert e["beschreibung"] == "Kaution hinterlegt bei Ausgabe"
    assert "id" in e
    assert "zeitstempel" in e
    assert "ausleihe_id" in e


def test_get_audit_thekendienst_erlaubt(client: TestClient):
    """0903 — Rolle thekendienst darf lesen."""
    resp = client.get("/audit", headers={"x-role": "thekendienst"})
    assert resp.status_code == 200


def test_get_audit_unbekannte_rolle_verboten(client: TestClient):
    """0903 — Unbekannte Rolle erhält 403."""
    resp = client.get("/audit", headers={"x-role": "mitglied"})
    assert resp.status_code == 403
    assert resp.json()["fehler_code"] == "ROLLE_UNZULAESSIG"


# ─────────────────────────────────────────────
#  GET /audit — Filter
# ─────────────────────────────────────────────


def test_get_audit_filter_art(client: TestClient, session: Session):
    """0903 — Filter art=hinterlegung liefert nur Hinterlegungen."""
    _, g, m, a = _erstelle_testdaten(session)
    erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.hinterlegung, 20, _JETZT)
    erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.freigabe, 20, _JETZT)

    resp = client.get("/audit?art=hinterlegung", headers={"x-role": "wart"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["eintraege"][0]["art"] == "hinterlegung"


def test_get_audit_filter_ausleihe_id(client: TestClient, session: Session):
    """0903 — Filter ausleihe_id liefert nur Einträge dieser Ausleihe."""
    k, g, m, a = _erstelle_testdaten(session)
    g2 = Gegenstand(inventarnummer="SB-001", kategorie_id=k.id, wiederbeschaffungswert_euro=50)
    session.add(g2)
    session.commit()
    session.refresh(g2)
    a2 = Ausleihe(
        gegenstand_id=g2.id,
        mitglied_id=m.id,
        ausgabe_datum=date(2026, 8, 24),
        rueckgabefrist=date(2026, 8, 31),
        kaution_betrag=10,
        status=AusleiheStatus.aktiv,
    )
    session.add(a2)
    session.commit()
    session.refresh(a2)

    erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.hinterlegung, 20, _JETZT)
    erfasse_kautionsbewegung(session, a2.id, KautionsbewegungArt.hinterlegung, 10, _JETZT)

    resp = client.get(f"/audit?ausleihe_id={a.id}", headers={"x-role": "wart"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["eintraege"][0]["ausleihe_id"] == str(a.id)


def test_get_audit_filter_gegenstand_inventarnummer(client: TestClient, session: Session):
    """0903 — Filter gegenstand_inventarnummer."""
    _, g, m, a = _erstelle_testdaten(session)
    erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.hinterlegung, 20, _JETZT)

    resp = client.get("/audit?gegenstand_inventarnummer=BH-042", headers={"x-role": "wart"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp2 = client.get("/audit?gegenstand_inventarnummer=XX-000", headers={"x-role": "wart"})
    assert resp2.json()["total"] == 0


def test_get_audit_filter_mitglied_id(client: TestClient, session: Session):
    """0903 — Filter mitglied_id."""
    _, g, m, a = _erstelle_testdaten(session)
    erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.hinterlegung, 20, _JETZT)

    resp = client.get(f"/audit?mitglied_id={m.id}", headers={"x-role": "wart"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_get_audit_filter_von_bis(client: TestClient, session: Session):
    """0903 — Zeitraum-Filter von/bis."""
    _, g, m, a = _erstelle_testdaten(session)
    erfasse_kautionsbewegung(
        session, a.id, KautionsbewegungArt.hinterlegung, 20,
        datetime(2026, 8, 24, 10, 0, 0),
    )
    erfasse_kautionsbewegung(
        session, a.id, KautionsbewegungArt.freigabe, 20,
        datetime(2026, 9, 1, 10, 0, 0),
    )

    resp = client.get("/audit?von=2026-08-24&bis=2026-08-31", headers={"x-role": "wart"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["eintraege"][0]["art"] == "hinterlegung"


def test_get_audit_zeitraum_ungueltig(client: TestClient):
    """0903 — von > bis liefert 400 ZEITRAUM_UNGUELTIG."""
    resp = client.get("/audit?von=2026-08-31&bis=2026-08-01", headers={"x-role": "wart"})
    assert resp.status_code == 400
    assert resp.json()["fehler_code"] == "ZEITRAUM_UNGUELTIG"


def test_get_audit_paginierung(client: TestClient, session: Session):
    """0903 — limit und offset werden korrekt angewendet."""
    _, g, m, a = _erstelle_testdaten(session)
    for _ in range(5):
        erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.hinterlegung, 20, _JETZT)

    resp = client.get("/audit?limit=2&offset=1", headers={"x-role": "wart"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["eintraege"]) == 2


# ─────────────────────────────────────────────
#  GET /audit/{id}
# ─────────────────────────────────────────────


def test_get_audit_by_id(client: TestClient, session: Session):
    """0903 — Einzelner Eintrag per ID abrufbar."""
    _, g, m, a = _erstelle_testdaten(session)
    b = erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.hinterlegung, 20, _JETZT)

    resp = client.get(f"/audit/{b.id}", headers={"x-role": "wart"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(b.id)
    assert body["art"] == "hinterlegung"
    assert body["betrag_euro"] == 20


def test_get_audit_by_id_nicht_gefunden(client: TestClient):
    """0903 — Unbekannte ID liefert 404 AUDIT_EINTRAG_NICHT_GEFUNDEN."""
    resp = client.get(f"/audit/{uuid.uuid4()}", headers={"x-role": "wart"})
    assert resp.status_code == 404
    assert resp.json()["fehler_code"] == "AUDIT_EINTRAG_NICHT_GEFUNDEN"


def test_get_audit_by_id_rolle_verboten(client: TestClient):
    """0903 — Fehlende Rolle liefert 403."""
    resp = client.get(f"/audit/{uuid.uuid4()}", headers={"x-role": "gast"})
    assert resp.status_code == 403


# ─────────────────────────────────────────────
#  BR-22: Kein Schreiben/Löschen auf /audit
# ─────────────────────────────────────────────


def test_post_audit_nicht_erlaubt(client: TestClient):
    """0903 — POST /audit ist nicht erlaubt (405)."""
    resp = client.post("/audit", json={}, headers={"x-role": "wart"})
    assert resp.status_code == 405


def test_delete_audit_nicht_erlaubt(client: TestClient):
    """0903 — DELETE /audit/{id} ist nicht erlaubt (405)."""
    resp = client.delete(f"/audit/{uuid.uuid4()}", headers={"x-role": "wart"})
    assert resp.status_code == 405


def test_put_audit_nicht_erlaubt(client: TestClient):
    """0903 — PUT /audit/{id} ist nicht erlaubt (405)."""
    resp = client.put(f"/audit/{uuid.uuid4()}", json={}, headers={"x-role": "wart"})
    assert resp.status_code == 405
