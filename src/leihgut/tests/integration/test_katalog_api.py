"""Integrationstests für EPIC-0100: Katalog verwalten.

Nutzt das client-Fixture aus conftest.py (In-Memory SQLite, TestClient).
Jeder Test referenziert seine Issue-ID als Kommentar.
"""

import uuid

import pytest


# ─────────────────────────────────────────────
#  Hilfsfunktionen
# ─────────────────────────────────────────────


def _erstelle_kategorie(client, name="Bohrhammer", leihdauer=7, wartung=10, einweisung=False):
    return client.post(
        "/kategorien",
        json={
            "name": name,
            "leihdauerTage": leihdauer,
            "wartungsintervallAusleihen": wartung,
            "einweisungspflichtig": einweisung,
        },
        headers={"X-Role": "wart"},
    )


def _erstelle_gegenstand(client, inventarnummer, kategorie_id, wbw=200):
    return client.post(
        "/gegenstaende",
        json={
            "inventarnummer": inventarnummer,
            "kategorieId": str(kategorie_id),
            "wiederbeschaffungswert": wbw,
        },
        headers={"X-Role": "wart"},
    )


# ─────────────────────────────────────────────
#  POST /kategorien — Story 0101
# ─────────────────────────────────────────────


def test_kategorie_anlegen_happy_path(client):
    # 0101
    resp = _erstelle_kategorie(client, name="Kettensäge", leihdauer=7, wartung=10, einweisung=True)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Kettensäge"
    assert body["leihdauerTage"] == 7
    assert body["wartungsintervallAusleihen"] == 10
    assert body["einweisungspflichtig"] is True
    assert uuid.UUID(body["kategorieId"])  # valide UUID


def test_kategorie_anlegen_falsche_rolle(client):
    # 0101
    resp = client.post(
        "/kategorien",
        json={"name": "Leiter", "leihdauerTage": 3, "wartungsintervallAusleihen": 5},
        headers={"X-Role": "mitglied"},
    )
    assert resp.status_code == 403
    assert resp.json()["fehler_code"] == "ROLLE_UNZULAESSIG"


def test_kategorie_anlegen_thekendienst_verboten(client):
    # 0101
    resp = client.post(
        "/kategorien",
        json={"name": "Leiter", "leihdauerTage": 3, "wartungsintervallAusleihen": 5},
        headers={"X-Role": "thekendienst"},
    )
    assert resp.status_code == 403


def test_kategorie_anlegen_name_doppelt(client):
    # 0101
    _erstelle_kategorie(client, name="Bohrhammer")
    resp = _erstelle_kategorie(client, name="Bohrhammer")
    assert resp.status_code == 409
    assert resp.json()["fehler_code"] == "KATEGORIE_NAME_DOPPELT"


def test_kategorie_anlegen_ungueltige_eingabe(client):
    # 0101
    resp = client.post(
        "/kategorien",
        json={"name": "X", "leihdauerTage": 0, "wartungsintervallAusleihen": 5},
        headers={"X-Role": "wart"},
    )
    assert resp.status_code == 400
    assert resp.json()["fehler_code"] == "EINGABE_UNGUELTIG"


# ─────────────────────────────────────────────
#  GET /kategorien — Story 0104
# ─────────────────────────────────────────────


def test_kategorien_liste_leer(client):
    # 0104
    resp = client.get("/kategorien", headers={"X-Role": "thekendienst"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_kategorien_liste_mit_eintraegen(client):
    # 0104
    _erstelle_kategorie(client, name="Schleifer")
    _erstelle_kategorie(client, name="Fräse")
    resp = client.get("/kategorien", headers={"X-Role": "wart"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_kategorien_filter_einweisungspflichtig(client):
    # 0104
    _erstelle_kategorie(client, name="Kettensäge", einweisung=True)
    _erstelle_kategorie(client, name="Bohrmaschine", einweisung=False)
    resp = client.get("/kategorien?einweisungspflichtig=true", headers={"X-Role": "wart"})
    assert resp.status_code == 200
    ergebnisse = resp.json()
    assert len(ergebnisse) == 1
    assert ergebnisse[0]["name"] == "Kettensäge"


def test_kategorien_liste_mitglied_verboten(client):
    # 0104
    resp = client.get("/kategorien", headers={"X-Role": "mitglied"})
    assert resp.status_code == 403


# ─────────────────────────────────────────────
#  GET /kategorien/{id} — Story 0104
# ─────────────────────────────────────────────


def test_kategorie_abrufen_gefunden(client):
    # 0104
    erstellt = _erstelle_kategorie(client, name="Fräse").json()
    resp = client.get(f"/kategorien/{erstellt['kategorieId']}", headers={"X-Role": "wart"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Fräse"


def test_kategorie_abrufen_nicht_gefunden(client):
    # 0104
    resp = client.get(f"/kategorien/{uuid.uuid4()}", headers={"X-Role": "thekendienst"})
    assert resp.status_code == 404
    assert resp.json()["fehler_code"] == "KATEGORIE_NICHT_GEFUNDEN"


def test_kategorie_abrufen_mitglied_verboten(client):
    # 0104
    resp = client.get(f"/kategorien/{uuid.uuid4()}", headers={"X-Role": "mitglied"})
    assert resp.status_code == 403


# ─────────────────────────────────────────────
#  PUT /kategorien/{id} — Story 0103
# ─────────────────────────────────────────────


def test_kategorie_aktualisieren_happy_path(client):
    # 0103
    erstellt = _erstelle_kategorie(client, name="Alt", leihdauer=3, wartung=5).json()
    kid = erstellt["kategorieId"]
    resp = client.put(
        f"/kategorien/{kid}",
        json={"name": "Neu", "leihdauerTage": 14, "wartungsintervallAusleihen": 20},
        headers={"X-Role": "wart"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Neu"
    assert body["leihdauerTage"] == 14


def test_kategorie_aktualisieren_nicht_gefunden(client):
    # 0103
    resp = client.put(
        f"/kategorien/{uuid.uuid4()}",
        json={"name": "X", "leihdauerTage": 7, "wartungsintervallAusleihen": 5},
        headers={"X-Role": "wart"},
    )
    assert resp.status_code == 404


def test_kategorie_aktualisieren_name_doppelt(client):
    # 0103
    _erstelle_kategorie(client, name="Bohrmaschine")
    kid = _erstelle_kategorie(client, name="Fräse").json()["kategorieId"]
    resp = client.put(
        f"/kategorien/{kid}",
        json={"name": "Bohrmaschine", "leihdauerTage": 7, "wartungsintervallAusleihen": 5},
        headers={"X-Role": "wart"},
    )
    assert resp.status_code == 409
    assert resp.json()["fehler_code"] == "KATEGORIE_NAME_DOPPELT"


def test_kategorie_aktualisieren_gleicher_name_erlaubt(client):
    # 0103 — PUT mit eigenem Namen ist kein Duplikat
    erstellt = _erstelle_kategorie(client, name="Fräse", leihdauer=7, wartung=10).json()
    kid = erstellt["kategorieId"]
    resp = client.put(
        f"/kategorien/{kid}",
        json={"name": "Fräse", "leihdauerTage": 14, "wartungsintervallAusleihen": 10},
        headers={"X-Role": "wart"},
    )
    assert resp.status_code == 200
    assert resp.json()["leihdauerTage"] == 14


# ─────────────────────────────────────────────
#  POST /gegenstaende — Story 0102
# ─────────────────────────────────────────────


def test_gegenstand_anlegen_happy_path(client):
    # 0102
    kid = _erstelle_kategorie(client, name="Bohrhammer").json()["kategorieId"]
    resp = _erstelle_gegenstand(client, "INV-00042", kid, wbw=200)
    assert resp.status_code == 201
    body = resp.json()
    assert body["inventarnummer"] == "INV-00042"
    assert body["kategorieId"] == kid
    assert body["kategorieName"] == "Bohrhammer"
    assert body["wiederbeschaffungswert"] == 200
    assert body["kaution"] == 40  # BR-04: 200 * 0.20 = 40
    assert body["zustand"] == "verfügbar"
    assert body["nutzungszaehler"] == 0


def test_gegenstand_anlegen_kaution_minimum(client):
    # 0102 BR-04: WBW=10 → Kaution=5 (Minimum)
    kid = _erstelle_kategorie(client).json()["kategorieId"]
    resp = _erstelle_gegenstand(client, "INV-00001", kid, wbw=10)
    assert resp.status_code == 201
    assert resp.json()["kaution"] == 5


def test_gegenstand_anlegen_kaution_maximum(client):
    # 0102 BR-04: WBW=600 → Kaution=100 (Maximum)
    kid = _erstelle_kategorie(client).json()["kategorieId"]
    resp = _erstelle_gegenstand(client, "INV-00002", kid, wbw=600)
    assert resp.status_code == 201
    assert resp.json()["kaution"] == 100


def test_gegenstand_anlegen_kategorie_nicht_gefunden(client):
    # 0102
    resp = _erstelle_gegenstand(client, "INV-00099", str(uuid.uuid4()), wbw=100)
    assert resp.status_code == 404
    assert resp.json()["fehler_code"] == "KATEGORIE_NICHT_GEFUNDEN"


def test_gegenstand_anlegen_inventarnummer_doppelt(client):
    # 0102
    kid = _erstelle_kategorie(client).json()["kategorieId"]
    _erstelle_gegenstand(client, "INV-00042", kid)
    resp = _erstelle_gegenstand(client, "INV-00042", kid)
    assert resp.status_code == 409
    assert resp.json()["fehler_code"] == "INVENTARNUMMER_DOPPELT"


def test_gegenstand_anlegen_falsche_rolle(client):
    # 0102
    kid = _erstelle_kategorie(client).json()["kategorieId"]
    resp = client.post(
        "/gegenstaende",
        json={"inventarnummer": "INV-X", "kategorieId": kid, "wiederbeschaffungswert": 100},
        headers={"X-Role": "thekendienst"},
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────
#  GET /gegenstaende — Story 0104
# ─────────────────────────────────────────────


def test_gegenstaende_liste(client):
    # 0104
    kid = _erstelle_kategorie(client).json()["kategorieId"]
    _erstelle_gegenstand(client, "INV-A", kid)
    _erstelle_gegenstand(client, "INV-B", kid)
    resp = client.get("/gegenstaende", headers={"X-Role": "thekendienst"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_gegenstaende_filter_kategorie(client):
    # 0104
    k1 = _erstelle_kategorie(client, name="Typ1").json()["kategorieId"]
    k2 = _erstelle_kategorie(client, name="Typ2").json()["kategorieId"]
    _erstelle_gegenstand(client, "INV-1", k1)
    _erstelle_gegenstand(client, "INV-2", k2)
    resp = client.get(f"/gegenstaende?kategorieId={k1}", headers={"X-Role": "wart"})
    assert resp.status_code == 200
    ergebnisse = resp.json()
    assert len(ergebnisse) == 1
    assert ergebnisse[0]["inventarnummer"] == "INV-1"


def test_gegenstaende_filter_zustand(client):
    # 0104
    kid = _erstelle_kategorie(client).json()["kategorieId"]
    _erstelle_gegenstand(client, "INV-Z", kid)
    resp = client.get("/gegenstaende?zustand=verfügbar", headers={"X-Role": "wart"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ─────────────────────────────────────────────
#  GET /gegenstaende/{inventarnummer} — Story 0104
# ─────────────────────────────────────────────


def test_gegenstand_abrufen_gefunden(client):
    # 0104
    kid = _erstelle_kategorie(client).json()["kategorieId"]
    _erstelle_gegenstand(client, "INV-00042", kid, wbw=350)
    resp = client.get("/gegenstaende/INV-00042", headers={"X-Role": "thekendienst"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["inventarnummer"] == "INV-00042"
    assert body["kaution"] == 70  # BR-04: 350 * 0.20 = 70


def test_gegenstand_abrufen_nicht_gefunden(client):
    # 0104
    resp = client.get("/gegenstaende/INV-UNBEKANNT", headers={"X-Role": "wart"})
    assert resp.status_code == 404
    assert resp.json()["fehler_code"] == "GEGENSTAND_NICHT_GEFUNDEN"


# ─────────────────────────────────────────────
#  PATCH /gegenstaende/{inventarnummer} — Story 0103
# ─────────────────────────────────────────────


def test_gegenstand_patch_wbw(client):
    # 0103
    kid = _erstelle_kategorie(client).json()["kategorieId"]
    _erstelle_gegenstand(client, "INV-P", kid, wbw=200)
    resp = client.patch(
        "/gegenstaende/INV-P",
        json={"wiederbeschaffungswert": 400},
        headers={"X-Role": "wart"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["wiederbeschaffungswert"] == 400
    assert body["kaution"] == 80  # BR-04: 400 * 0.20 = 80


def test_gegenstand_patch_nicht_gefunden(client):
    # 0103
    resp = client.patch(
        "/gegenstaende/INV-NEIN",
        json={"wiederbeschaffungswert": 100},
        headers={"X-Role": "wart"},
    )
    assert resp.status_code == 404


def test_gegenstand_patch_falsche_rolle(client):
    # 0103
    kid = _erstelle_kategorie(client).json()["kategorieId"]
    _erstelle_gegenstand(client, "INV-Q", kid)
    resp = client.patch(
        "/gegenstaende/INV-Q",
        json={"wiederbeschaffungswert": 100},
        headers={"X-Role": "thekendienst"},
    )
    assert resp.status_code == 403
