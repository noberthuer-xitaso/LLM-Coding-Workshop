"""Integrationstests für Einweisungen und Mitglieder-Endpunkte.

Issues: 0201, 0202, 0203
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from leihgut.domain.models import Kategorie, Mitglied


# ─────────────────────────────────────────────
#  Hilfsfunktionen
# ─────────────────────────────────────────────


def _erstelle_mitglied(session: Session, name: str = "Sabine") -> Mitglied:
    m = Mitglied(name=name)
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def _erstelle_kategorie(session: Session, name: str = "Kettensäge", einweisungspflichtig: bool = True) -> Kategorie:
    k = Kategorie(name=name, leihdauer_tage=7, wartungsintervall_ausleihen=10, einweisungspflichtig=einweisungspflichtig)
    session.add(k)
    session.commit()
    session.refresh(k)
    return k


# ─────────────────────────────────────────────
#  Mitglieder
# ─────────────────────────────────────────────


def test_mitglied_anlegen(client: TestClient):  # 0201
    res = client.post("/mitglieder", json={"name": "Sabine"}, headers={"X-Role": "thekendienst"})
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Sabine"
    assert "mitgliedId" in data


def test_mitglied_abfragen(client: TestClient, session: Session):  # 0201
    m = _erstelle_mitglied(session)
    res = client.get(f"/mitglieder/{m.id}", headers={"X-Role": "thekendienst"})
    assert res.status_code == 200
    assert res.json()["name"] == "Sabine"


def test_mitglied_nicht_gefunden(client: TestClient):  # 0201
    res = client.get(f"/mitglieder/{uuid.uuid4()}", headers={"X-Role": "thekendienst"})
    assert res.status_code == 404
    assert res.json()["fehler_code"] == "MITGLIED_NICHT_GEFUNDEN"


def test_mitglied_anlegen_falsche_rolle(client: TestClient):  # 0201
    res = client.post("/mitglieder", json={"name": "X"}, headers={"X-Role": "mitglied"})
    assert res.status_code == 403


# ─────────────────────────────────────────────
#  Einweisung anlegen (0201)
# ─────────────────────────────────────────────


def test_einweisung_anlegen(client: TestClient, session: Session):  # 0201
    m = _erstelle_mitglied(session)
    k = _erstelle_kategorie(session)
    res = client.post(
        "/einweisungen",
        json={"mitgliedId": str(m.id), "kategorieId": str(k.id)},
        headers={"X-Role": "wart"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["mitgliedId"] == str(m.id)
    assert data["kategorieId"] == str(k.id)
    assert data["kategorieName"] == "Kettensäge"
    assert "einweisungId" in data


def test_einweisung_doppelt_abgelehnt(client: TestClient, session: Session):  # 0201 BR-08
    m = _erstelle_mitglied(session)
    k = _erstelle_kategorie(session)
    payload = {"mitgliedId": str(m.id), "kategorieId": str(k.id)}
    headers = {"X-Role": "wart"}
    client.post("/einweisungen", json=payload, headers=headers)
    res = client.post("/einweisungen", json=payload, headers=headers)
    assert res.status_code == 409
    assert res.json()["fehler_code"] == "EINWEISUNG_BEREITS_VORHANDEN"


def test_einweisung_mitglied_nicht_gefunden(client: TestClient, session: Session):  # 0201
    k = _erstelle_kategorie(session)
    res = client.post(
        "/einweisungen",
        json={"mitgliedId": str(uuid.uuid4()), "kategorieId": str(k.id)},
        headers={"X-Role": "wart"},
    )
    assert res.status_code == 404
    assert res.json()["fehler_code"] == "MITGLIED_NICHT_GEFUNDEN"


def test_einweisung_kategorie_nicht_gefunden(client: TestClient, session: Session):  # 0201
    m = _erstelle_mitglied(session)
    res = client.post(
        "/einweisungen",
        json={"mitgliedId": str(m.id), "kategorieId": str(uuid.uuid4())},
        headers={"X-Role": "wart"},
    )
    assert res.status_code == 404
    assert res.json()["fehler_code"] == "KATEGORIE_NICHT_GEFUNDEN"


def test_einweisung_anlegen_falsche_rolle(client: TestClient, session: Session):  # 0201
    m = _erstelle_mitglied(session)
    k = _erstelle_kategorie(session)
    res = client.post(
        "/einweisungen",
        json={"mitgliedId": str(m.id), "kategorieId": str(k.id)},
        headers={"X-Role": "thekendienst"},
    )
    assert res.status_code == 403


# ─────────────────────────────────────────────
#  Einweisungen abfragen (0202)
# ─────────────────────────────────────────────


def test_einweisungen_abfragen_nach_mitglied(client: TestClient, session: Session):  # 0202
    m = _erstelle_mitglied(session)
    k1 = _erstelle_kategorie(session, "Bohrer")
    k2 = _erstelle_kategorie(session, "Säge")
    headers = {"X-Role": "wart"}
    client.post("/einweisungen", json={"mitgliedId": str(m.id), "kategorieId": str(k1.id)}, headers=headers)
    client.post("/einweisungen", json={"mitgliedId": str(m.id), "kategorieId": str(k2.id)}, headers=headers)

    res = client.get(f"/einweisungen?mitglied_id={m.id}", headers={"X-Role": "thekendienst"})
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_einweisungen_nach_mitglied_leer(client: TestClient, session: Session):  # 0202
    m = _erstelle_mitglied(session)
    res = client.get(f"/mitglieder/{m.id}/einweisungen", headers={"X-Role": "thekendienst"})
    assert res.status_code == 200
    assert res.json() == []


def test_einweisungen_nach_kategorie(client: TestClient, session: Session):  # 0202
    m1 = _erstelle_mitglied(session, "A")
    m2 = _erstelle_mitglied(session, "B")
    k = _erstelle_kategorie(session)
    headers = {"X-Role": "wart"}
    client.post("/einweisungen", json={"mitgliedId": str(m1.id), "kategorieId": str(k.id)}, headers=headers)
    client.post("/einweisungen", json={"mitgliedId": str(m2.id), "kategorieId": str(k.id)}, headers=headers)

    res = client.get(f"/einweisungen?kategorie_id={k.id}", headers={"X-Role": "wart"})
    assert res.status_code == 200
    assert len(res.json()) == 2


# ─────────────────────────────────────────────
#  Einweisung widerrufen (0203)
# ─────────────────────────────────────────────


def test_einweisung_loeschen(client: TestClient, session: Session):  # 0203
    m = _erstelle_mitglied(session)
    k = _erstelle_kategorie(session)
    res = client.post(
        "/einweisungen",
        json={"mitgliedId": str(m.id), "kategorieId": str(k.id)},
        headers={"X-Role": "wart"},
    )
    eid = res.json()["einweisungId"]
    del_res = client.delete(f"/einweisungen/{eid}", headers={"X-Role": "wart"})
    assert del_res.status_code == 204

    # Nach Widerruf ist die Einweisung weg
    list_res = client.get(f"/einweisungen?mitglied_id={m.id}", headers={"X-Role": "wart"})
    assert list_res.json() == []


def test_einweisung_loeschen_nicht_gefunden(client: TestClient):  # 0203
    res = client.delete(f"/einweisungen/{uuid.uuid4()}", headers={"X-Role": "wart"})
    assert res.status_code == 404
    assert res.json()["fehler_code"] == "EINWEISUNG_NICHT_GEFUNDEN"


def test_einweisung_loeschen_falsche_rolle(client: TestClient, session: Session):  # 0203
    m = _erstelle_mitglied(session)
    k = _erstelle_kategorie(session)
    res = client.post(
        "/einweisungen",
        json={"mitgliedId": str(m.id), "kategorieId": str(k.id)},
        headers={"X-Role": "wart"},
    )
    eid = res.json()["einweisungId"]
    del_res = client.delete(f"/einweisungen/{eid}", headers={"X-Role": "thekendienst"})
    assert del_res.status_code == 403
