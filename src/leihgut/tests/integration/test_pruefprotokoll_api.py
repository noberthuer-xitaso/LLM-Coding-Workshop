"""Integrationstests für EPIC-0400: Rückgabe & Prüfung, EPIC-0500: Kaution.

Issue: # 0401, # 0402, # 0403, # 0501, # 0502, # 0503, # 0504
Nutzt das client-Fixture aus conftest.py (In-Memory SQLite, TestClient).
"""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlmodel import Session

from leihgut.application import ausleihe as ausleihe_app
from leihgut.application import pruefprotokoll as pp_app
from leihgut.domain.models import (
    Ausleihe,
    AusleiheStatus,
    Gegenstand,
    GegenstandZustand,
    Kategorie,
    Mitglied,
    Reservierung,
    Vormerkung,
    VormerkungStatus,
)
from leihgut.infrastructure.datum import FixesDatum

HEUTE = date(2026, 9, 1)
HEADERS_THEKE = {"x-role": "thekendienst"}
HEADERS_WART = {"x-role": "wart", "x-user": "wart-rolf"}


# ─────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def fixiere_datum():
    """Alle Tests laufen mit festem Datum 2026-09-01."""
    festes = FixesDatum(HEUTE)
    ausleihe_app.set_datumsquelle(festes)
    pp_app.set_datumsquelle(festes)
    yield
    ausleihe_app.set_datumsquelle(ausleihe_app.SystemDatumsQuelle())
    pp_app.set_datumsquelle(pp_app.SystemDatumsQuelle())


def _kategorie(session: Session, *, name="Bohrmaschine", leihdauer=14, intervall=10) -> Kategorie:
    k = Kategorie(name=name, leihdauer_tage=leihdauer, wartungsintervall_ausleihen=intervall)
    session.add(k)
    session.commit()
    session.refresh(k)
    return k


def _gegenstand(
    session: Session,
    kategorie: Kategorie,
    *,
    inventarnummer="INV-001",
    wbw=200,
    zustand=GegenstandZustand.ausgeliehen,
    nutzungszaehler=0,
) -> Gegenstand:
    g = Gegenstand(
        inventarnummer=inventarnummer,
        kategorie_id=kategorie.id,
        wiederbeschaffungswert_euro=wbw,
        zustand=zustand,
        nutzungszaehler=nutzungszaehler,
    )
    session.add(g)
    session.commit()
    session.refresh(g)
    return g


def _mitglied(session: Session, name="Max Muster") -> Mitglied:
    m = Mitglied(name=name)
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def _ausleihe(
    session: Session,
    gegenstand: Gegenstand,
    mitglied: Mitglied,
    *,
    status=AusleiheStatus.aktiv,
    kaution=40,
    rueckgabefrist: date = None,
) -> Ausleihe:
    if rueckgabefrist is None:
        rueckgabefrist = HEUTE + timedelta(days=14)
    a = Ausleihe(
        gegenstand_id=gegenstand.id,
        mitglied_id=mitglied.id,
        ausgabe_datum=HEUTE - timedelta(days=7),
        rueckgabefrist=rueckgabefrist,
        kaution_betrag=kaution,
        status=status,
    )
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _ausleihe_in_pruefung(session, gegenstand, mitglied, *, kaution=40):
    """Hilfsfunktion: Ausleihe + Gegenstand direkt in in_Prüfung setzen."""
    gegenstand.zustand = GegenstandZustand.in_pruefung
    session.add(gegenstand)
    a = _ausleihe(session, gegenstand, mitglied, status=AusleiheStatus.in_pruefung, kaution=kaution)
    a.rueckgabe_datum = HEUTE
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


# ─────────────────────────────────────────────
#  0401: Rückgabe
# ─────────────────────────────────────────────


def test_rueckgabe_happy_path(client, session):
    """0401: Rückgabe setzt Ausleihe und Gegenstand in in_Prüfung."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)

    resp = client.post(f"/ausleihen/{a.id}/rueckgabe", headers=HEADERS_THEKE)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ausleiheId"] == str(a.id)
    assert body["zustand"] == "in_Prüfung"

    session.refresh(a)
    session.refresh(g)
    assert a.status == AusleiheStatus.in_pruefung
    assert a.rueckgabe_datum == HEUTE
    assert g.zustand == GegenstandZustand.in_pruefung


def test_rueckgabe_mit_auffaelligkeiten(client, session):
    """0401: Auffälligkeiten werden gespeichert."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)

    resp = client.post(
        f"/ausleihen/{a.id}/rueckgabe",
        json={"auffaelligkeiten": "Kratzer am Gehäuse"},
        headers=HEADERS_THEKE,
    )
    assert resp.status_code == 200
    session.refresh(a)
    assert a.auffaelligkeiten == "Kratzer am Gehäuse"


def test_rueckgabe_gegenstand_nicht_ausgeliehen(client, session):
    """0401: 409 wenn Ausleihe nicht aktiv."""
    k = _kategorie(session)
    g = _gegenstand(session, k, zustand=GegenstandZustand.in_pruefung)
    m = _mitglied(session)
    a = _ausleihe(session, g, m, status=AusleiheStatus.in_pruefung)

    resp = client.post(f"/ausleihen/{a.id}/rueckgabe", headers=HEADERS_THEKE)
    assert resp.status_code == 409
    assert resp.json()["fehler_code"] == "GEGENSTAND_NICHT_AUSGELIEHEN"


def test_rueckgabe_ausleihe_nicht_gefunden(client, session):
    """0401: 404 bei unbekannter Ausleihe."""
    resp = client.post(f"/ausleihen/{uuid.uuid4()}/rueckgabe", headers=HEADERS_THEKE)
    assert resp.status_code == 404


def test_rueckgabe_rolle_nicht_berechtigt(client, session):
    """0401: 403 für wart-Rolle."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)

    resp = client.post(f"/ausleihen/{a.id}/rueckgabe", headers={"x-role": "wart"})
    assert resp.status_code == 403


# ─────────────────────────────────────────────
#  0402: Prüfprotokoll erstellen
# ─────────────────────────────────────────────


def test_pruefprotokoll_happy_path_ohne_abzug(client, session):
    """0402/0502: Prüfprotokoll ohne Kautionsabzug — volle Freigabe."""
    k = _kategorie(session)
    g = _gegenstand(session, k, zustand=GegenstandZustand.in_pruefung)
    m = _mitglied(session)
    a = _ausleihe_in_pruefung(session, g, m, kaution=40)

    resp = client.post(
        f"/ausleihen/{a.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 0},
        headers=HEADERS_WART,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["nachzustandEingabe"] == "verfügbar"
    assert body["nachzustandEffektiv"] == "verfügbar"
    assert body["kautionsabzug"] == 0
    assert body["kautionFreigegeben"] == 40
    assert body["reserviertFuer"] is None

    session.refresh(a)
    session.refresh(g)
    assert a.status == AusleiheStatus.abgeschlossen
    assert g.zustand == GegenstandZustand.verfuegbar


def test_pruefprotokoll_mit_kautionsabzug(client, session):
    """0402/0502: Kautionsabzug 10 von 40 → Freigabe 30."""
    k = _kategorie(session)
    g = _gegenstand(session, k, zustand=GegenstandZustand.in_pruefung)
    m = _mitglied(session)
    a = _ausleihe_in_pruefung(session, g, m, kaution=40)

    resp = client.post(
        f"/ausleihen/{a.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 10, "begruendung": "Kleiner Kratzer"},
        headers=HEADERS_WART,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kautionsabzug"] == 10
    assert body["kautionFreigegeben"] == 30
    assert body["begruendung"] == "Kleiner Kratzer"


def test_pruefprotokoll_wartungsfaellig_durch_intervall(client, session):
    """0402, BR-24: nutzungszaehler 9 + 1 = 10 == intervall → wartungsfällig."""
    k = _kategorie(session, intervall=10)
    g = _gegenstand(session, k, zustand=GegenstandZustand.in_pruefung, nutzungszaehler=9)
    m = _mitglied(session)
    a = _ausleihe_in_pruefung(session, g, m, kaution=40)

    resp = client.post(
        f"/ausleihen/{a.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 0},
        headers=HEADERS_WART,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Eingabe war verfügbar, effektiv wartungsfällig (BR-24 überschreibt)
    assert body["nachzustandEingabe"] == "verfügbar"
    assert body["nachzustandEffektiv"] == "wartungsfällig"

    session.refresh(g)
    assert g.zustand == GegenstandZustand.wartungsfaellig
    assert g.nutzungszaehler == 10


def test_pruefprotokoll_verloren(client, session):
    """0402/0503: nachzustand verloren → ausgemustert, volle Kaution einbehalten."""
    k = _kategorie(session)
    g = _gegenstand(session, k, zustand=GegenstandZustand.in_pruefung)
    m = _mitglied(session)
    a = _ausleihe_in_pruefung(session, g, m, kaution=40)

    resp = client.post(
        f"/ausleihen/{a.id}/pruefprotokoll",
        json={"nachzustand": "verloren", "kautionsabzug": 0},
        headers=HEADERS_WART,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["nachzustandEingabe"] == "verloren"
    assert body["nachzustandEffektiv"] == "ausgemustert"
    assert body["kautionsabzug"] == 40
    assert body["kautionFreigegeben"] == 0

    session.refresh(g)
    assert g.zustand == GegenstandZustand.ausgemustert


def test_pruefprotokoll_mit_vormerkung_reserviert(client, session):
    """0402/BR-30: Verfügbar + offene Vormerkung → reserviert für nächstes Mitglied."""
    k = _kategorie(session)
    g = _gegenstand(session, k, zustand=GegenstandZustand.in_pruefung)
    m1 = _mitglied(session, "Ausleiher")
    m2 = _mitglied(session, "Wartender")
    a = _ausleihe_in_pruefung(session, g, m1)

    # Vormerkung für m2
    vm = Vormerkung(
        mitglied_id=m2.id,
        kategorie_id=k.id,
        eingangszeit=datetime(2026, 8, 1, 10, 0),
    )
    session.add(vm)
    session.commit()

    resp = client.post(
        f"/ausleihen/{a.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 0},
        headers=HEADERS_WART,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["nachzustandEffektiv"] == "reserviert"
    assert body["reserviertFuer"] == str(m2.id)

    session.refresh(g)
    assert g.zustand == GegenstandZustand.reserviert

    # Vormerkung storniert
    session.refresh(vm)
    assert vm.status == VormerkungStatus.storniert


def test_pruefprotokoll_kautionsabzug_zu_hoch(client, session):
    """0402/BR-21: 422 wenn Kautionsabzug > hinterlegte Kaution."""
    k = _kategorie(session)
    g = _gegenstand(session, k, zustand=GegenstandZustand.in_pruefung)
    m = _mitglied(session)
    a = _ausleihe_in_pruefung(session, g, m, kaution=40)

    resp = client.post(
        f"/ausleihen/{a.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 50},
        headers=HEADERS_WART,
    )
    assert resp.status_code == 422
    assert resp.json()["fehler_code"] == "KAUTIONSABZUG_ZU_HOCH"


def test_pruefprotokoll_nicht_in_pruefung(client, session):
    """0402: 409 wenn Ausleihe nicht im Status in_Prüfung."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)

    resp = client.post(
        f"/ausleihen/{a.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 0},
        headers=HEADERS_WART,
    )
    assert resp.status_code == 409
    assert resp.json()["fehler_code"] == "GEGENSTAND_NICHT_IN_PRUEFUNG"


def test_pruefprotokoll_doppelt(client, session):
    """0402: 409 PRUEFPROTOKOLL_BEREITS_VORHANDEN wenn Protokoll schon existiert."""
    k = _kategorie(session)
    g = _gegenstand(session, k, zustand=GegenstandZustand.in_pruefung)
    m = _mitglied(session)
    a = _ausleihe_in_pruefung(session, g, m)

    # erstes Protokoll erstellen
    resp1 = client.post(
        f"/ausleihen/{a.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 0},
        headers=HEADERS_WART,
    )
    assert resp1.status_code == 201

    # Ausleihe manuell zurück auf in_Prüfung setzen (simuliert fehlerhafte Situation)
    session.refresh(a)
    a.status = AusleiheStatus.in_pruefung
    session.add(a)
    session.commit()

    # Zweites Protokoll → muss 409 PRUEFPROTOKOLL_BEREITS_VORHANDEN geben
    resp2 = client.post(
        f"/ausleihen/{a.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 0},
        headers=HEADERS_WART,
    )
    assert resp2.status_code == 409
    assert resp2.json()["fehler_code"] == "PRUEFPROTOKOLL_BEREITS_VORHANDEN"


def test_pruefprotokoll_vorheriges_protokoll(client, session):
    """0402/BR-16: vorherigePruefprotokoll enthält letztes Protokoll desselben Gegenstands."""
    k = _kategorie(session)
    g = _gegenstand(session, k, inventarnummer="INV-PREV", zustand=GegenstandZustand.in_pruefung)
    m = _mitglied(session)

    # Erste Ausleihe + Protokoll
    a1 = _ausleihe_in_pruefung(session, g, m)
    resp1 = client.post(
        f"/ausleihen/{a1.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 0},
        headers=HEADERS_WART,
    )
    assert resp1.status_code == 201
    protokoll1_id = resp1.json()["pruefprotokollId"]

    # Zweite Ausleihe: Gegenstand ist jetzt verfügbar, setze zurück auf ausgeliehen/in_pruefung
    session.refresh(g)
    g.zustand = GegenstandZustand.in_pruefung
    session.add(g)
    session.commit()

    a2 = _ausleihe_in_pruefung(session, g, m)
    resp2 = client.post(
        f"/ausleihen/{a2.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 0},
        headers=HEADERS_WART,
    )
    assert resp2.status_code == 201, resp2.text
    assert resp2.json()["vorherigePruefprotokoll"] == protokoll1_id


# ─────────────────────────────────────────────
#  0403: Verloren erklären
# ─────────────────────────────────────────────


def test_verloren_erklaeren_happy_path(client, session):
    """0403/0503: Aktive Ausleihe als verloren erklären ohne Rückgabe."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)

    resp = client.post(f"/ausleihen/{a.id}/verloren", headers=HEADERS_WART)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["nachzustandEingabe"] == "verloren"
    assert body["nachzustandEffektiv"] == "ausgemustert"
    assert body["kautionsabzug"] == 40
    assert body["kautionFreigegeben"] == 0

    session.refresh(a)
    session.refresh(g)
    assert a.status == AusleiheStatus.abgeschlossen
    assert g.zustand == GegenstandZustand.ausgemustert


def test_verloren_erklaeren_nicht_aktiv(client, session):
    """0403: 409 wenn Ausleihe nicht aktiv."""
    k = _kategorie(session)
    g = _gegenstand(session, k, zustand=GegenstandZustand.in_pruefung)
    m = _mitglied(session)
    a = _ausleihe(session, g, m, status=AusleiheStatus.in_pruefung)

    resp = client.post(f"/ausleihen/{a.id}/verloren", headers=HEADERS_WART)
    assert resp.status_code == 409
    assert resp.json()["fehler_code"] == "AUSLEIHE_NICHT_AKTIV"


def test_verloren_erklaeren_protokoll_bereits_vorhanden(client, session):
    """0403: 409 wenn Prüfprotokoll bereits vorhanden."""
    k = _kategorie(session)
    g = _gegenstand(session, k, zustand=GegenstandZustand.in_pruefung)
    m = _mitglied(session)
    a = _ausleihe_in_pruefung(session, g, m)

    # Erst Prüfprotokoll erstellen
    client.post(
        f"/ausleihen/{a.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 0},
        headers=HEADERS_WART,
    )

    # Neue aktive Ausleihe mit bestehendem Protokoll: wir müssen status auf aktiv und
    # Protokoll existiert bereits — das geht nicht ohne weitere Ausleihe.
    # Stattdessen: erstelle frische aktive Ausleihe und setze manuell Protokoll
    from leihgut.domain.models import Pruefprotokoll, PruefprotokollNachzustand

    g2 = _gegenstand(session, k, inventarnummer="INV-002")
    a2 = _ausleihe(session, g2, m, status=AusleiheStatus.aktiv)
    # Simuliere ein vorhandenes Protokoll für a2
    pp = Pruefprotokoll(
        ausleihe_id=a2.id,
        wart_id="wart",
        erstellt_am=datetime.now(),
        kautionsabzug=0,
        nachzustand=PruefprotokollNachzustand.verfuegbar,
    )
    session.add(pp)
    session.commit()

    resp = client.post(f"/ausleihen/{a2.id}/verloren", headers=HEADERS_WART)
    assert resp.status_code == 409
    assert resp.json()["fehler_code"] == "PRUEFPROTOKOLL_BEREITS_VORHANDEN"


# ─────────────────────────────────────────────
#  0501: Kaution bei Ausgabe hinterlegen (Wave 5 — nur Test)
# ─────────────────────────────────────────────


def test_kaution_hinterlegung_bei_ausgabe(client, session):
    """0501: Ausleihe anlegen legt Kautionsbewegung 'hinterlegung' an."""
    k = _kategorie(session)
    g = _gegenstand(session, k, zustand=GegenstandZustand.verfuegbar)
    m = _mitglied(session)

    resp = client.post(
        "/ausleihen",
        json={"gegenstandId": g.inventarnummer, "mitgliedId": str(m.id)},
        headers={"x-role": "thekendienst"},
    )
    assert resp.status_code == 201, resp.text

    # Kautionsbewegung prüfen
    resp_kb = client.get(
        f"/mitglieder/{m.id}/kautionsbewegungen",
        headers={"x-role": "wart"},
    )
    assert resp_kb.status_code == 200
    bewegungen = resp_kb.json()
    assert any(b["art"] == "hinterlegung" for b in bewegungen)


# ─────────────────────────────────────────────
#  0504: Kautionsbewegungen abfragen
# ─────────────────────────────────────────────


def test_kautionsbewegungen_nach_pruefprotokoll(client, session):
    """0504/0502: Kautionsbewegungen enthalten Abzug + Freigabe nach Prüfprotokoll."""
    k = _kategorie(session)
    g = _gegenstand(session, k, zustand=GegenstandZustand.in_pruefung)
    m = _mitglied(session)
    a = _ausleihe_in_pruefung(session, g, m, kaution=40)

    client.post(
        f"/ausleihen/{a.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 10},
        headers=HEADERS_WART,
    )

    resp = client.get(f"/mitglieder/{m.id}/kautionsbewegungen", headers={"x-role": "wart"})
    assert resp.status_code == 200
    bewegungen = resp.json()
    arten = {b["art"] for b in bewegungen}
    assert "abzug" in arten
    assert "freigabe" in arten

    abzug = next(b for b in bewegungen if b["art"] == "abzug")
    freigabe = next(b for b in bewegungen if b["art"] == "freigabe")
    assert abzug["betrag"] == 10
    assert freigabe["betrag"] == 30
    assert abzug["pruefprotokollId"] is not None


def test_kautionsbewegungen_nach_verlust(client, session):
    """0504/0503: Kautionsbewegung 'einbehaltung' bei Verlust."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m, kaution=40)

    client.post(f"/ausleihen/{a.id}/verloren", headers=HEADERS_WART)

    resp = client.get(f"/mitglieder/{m.id}/kautionsbewegungen", headers={"x-role": "wart"})
    assert resp.status_code == 200
    bewegungen = resp.json()
    arten = {b["art"] for b in bewegungen}
    assert "einbehaltung" in arten

    einbehaltung = next(b for b in bewegungen if b["art"] == "einbehaltung")
    assert einbehaltung["betrag"] == 40


def test_kautionsbewegungen_filter_ausleihe(client, session):
    """0504: Filter nach ausleihe_id liefert nur Bewegungen dieser Ausleihe."""
    k = _kategorie(session)
    g1 = _gegenstand(session, k, inventarnummer="INV-F1")
    g2 = _gegenstand(session, k, inventarnummer="INV-F2")
    m = _mitglied(session)

    a1 = _ausleihe(session, g1, m)
    a2 = _ausleihe(session, g2, m)

    client.post(f"/ausleihen/{a1.id}/verloren", headers=HEADERS_WART)
    g2.zustand = GegenstandZustand.in_pruefung
    session.add(g2)
    session.commit()
    a2.status = AusleiheStatus.in_pruefung
    a2.rueckgabe_datum = HEUTE
    session.add(a2)
    session.commit()
    client.post(
        f"/ausleihen/{a2.id}/pruefprotokoll",
        json={"nachzustand": "verfügbar", "kautionsabzug": 0},
        headers=HEADERS_WART,
    )

    resp = client.get(
        f"/mitglieder/{m.id}/kautionsbewegungen",
        params={"ausleihe_id": str(a1.id)},
        headers={"x-role": "wart"},
    )
    assert resp.status_code == 200
    bewegungen = resp.json()
    assert all(b["ausleiheId"] == str(a1.id) for b in bewegungen)


def test_kautionsbewegungen_mitglied_nicht_gefunden(client, session):
    """0504: 404 für unbekanntes Mitglied."""
    resp = client.get(
        f"/mitglieder/{uuid.uuid4()}/kautionsbewegungen",
        headers={"x-role": "wart"},
    )
    assert resp.status_code == 404
    assert resp.json()["fehler_code"] == "MITGLIED_NICHT_GEFUNDEN"


def test_kautionsbewegungen_rolle_nicht_berechtigt(client, session):
    """0504: 403 für nicht-berechtigte Rolle."""
    m = _mitglied(session)
    resp = client.get(
        f"/mitglieder/{m.id}/kautionsbewegungen",
        headers={"x-role": "mitglied"},
    )
    assert resp.status_code == 403
