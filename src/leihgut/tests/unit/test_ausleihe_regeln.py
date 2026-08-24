"""Unit-Tests für Domänenregeln: Ausleihe + Verlängerung + Mitgliedersperre.

Issue: 0301, 0303, 0801, 0802
"""

from datetime import date

import pytest

from leihgut.domain.models import (
    Ausleihe,
    AusleiheStatus,
    Gegenstand,
    GegenstandZustand,
    Kategorie,
)
from leihgut.domain.regeln import (
    ist_mitglied_gesperrt,
    prüfe_ausgabebedingungen,
    prüfe_verlaengerungsbedingungen,
)

HEUTE = date(2026, 9, 1)


# ─────────────────────────────────────────────
#  Hilfsfunktionen
# ─────────────────────────────────────────────


def _make_ausleihe(rueckgabefrist: date, status=AusleiheStatus.aktiv, rueckgabe=None) -> Ausleihe:
    import uuid
    return Ausleihe(
        id=uuid.uuid4(),
        gegenstand_id=uuid.uuid4(),
        mitglied_id=uuid.uuid4(),
        ausgabe_datum=date(2026, 8, 1),
        rueckgabefrist=rueckgabefrist,
        rueckgabe_datum=rueckgabe,
        kaution_betrag=20,
        status=status,
    )


def _make_kategorie(einweisungspflichtig=False, leihdauer=14) -> Kategorie:
    import uuid
    return Kategorie(
        id=uuid.uuid4(),
        name="Testkat",
        leihdauer_tage=leihdauer,
        wartungsintervall_ausleihen=10,
        einweisungspflichtig=einweisungspflichtig,
    )


def _make_gegenstand(zustand=GegenstandZustand.verfuegbar, kategorie=None) -> Gegenstand:
    import uuid
    g = Gegenstand(
        id=uuid.uuid4(),
        inventarnummer="TEST-001",
        kategorie_id=uuid.uuid4(),
        wiederbeschaffungswert_euro=100,
        zustand=zustand,
    )
    g.kategorie = kategorie or _make_kategorie()
    return g


# ─────────────────────────────────────────────
#  ist_mitglied_gesperrt  — 0801
# ─────────────────────────────────────────────


def test_keine_ausleihen_nicht_gesperrt():
    # 0801
    assert ist_mitglied_gesperrt([], HEUTE) is False


def test_aktive_ausleihe_nicht_ueberfaellig_nicht_gesperrt():
    # 0801
    ausleihe = _make_ausleihe(rueckgabefrist=date(2026, 9, 15))
    assert ist_mitglied_gesperrt([ausleihe], HEUTE) is False


def test_aktive_ausleihe_ueberfaellig_gesperrt():
    # 0801
    ausleihe = _make_ausleihe(rueckgabefrist=date(2026, 8, 25))
    assert ist_mitglied_gesperrt([ausleihe], HEUTE) is True


def test_zurueckgegebene_ueberfaellige_ausleihe_nicht_gesperrt():
    # 0801: zurückgegeben = nicht gesperrt
    ausleihe = _make_ausleihe(
        rueckgabefrist=date(2026, 8, 25),
        rueckgabe=date(2026, 8, 30),
    )
    assert ist_mitglied_gesperrt([ausleihe], HEUTE) is False


def test_abgeschlossene_ausleihe_hebt_sperre_auf():
    # 0802: abgeschlossen = nicht aktiv → nicht gesperrt
    ausleihe = _make_ausleihe(
        rueckgabefrist=date(2026, 8, 25),
        status=AusleiheStatus.abgeschlossen,
    )
    assert ist_mitglied_gesperrt([ausleihe], HEUTE) is False


def test_mehrere_ausleihen_eine_ueberfaellig_gesperrt():
    # 0801
    a1 = _make_ausleihe(rueckgabefrist=date(2026, 9, 15))
    a2 = _make_ausleihe(rueckgabefrist=date(2026, 8, 20))
    assert ist_mitglied_gesperrt([a1, a2], HEUTE) is True


# ─────────────────────────────────────────────
#  prüfe_ausgabebedingungen  — 0301
# ─────────────────────────────────────────────


def test_ausgabe_alle_bedingungen_erfuellt():
    # 0301
    g = _make_gegenstand()
    gruende = prüfe_ausgabebedingungen(g, None, 0, False, True, False)
    assert gruende == []


def test_ausgabe_mitglied_gesperrt():
    # 0301
    g = _make_gegenstand()
    gruende = prüfe_ausgabebedingungen(g, None, 0, True, True, False)
    assert any("BR-07" in gr for gr in gruende)


def test_ausgabe_limit_erreicht():
    # 0301
    g = _make_gegenstand()
    gruende = prüfe_ausgabebedingungen(g, None, 3, False, True, False)
    assert any("BR-06" in gr for gr in gruende)


def test_ausgabe_gegenstand_nicht_verfuegbar():
    # 0301
    g = _make_gegenstand(zustand=GegenstandZustand.ausgeliehen)
    gruende = prüfe_ausgabebedingungen(g, None, 0, False, True, False)
    assert any("BR-05" in gr for gr in gruende)


def test_ausgabe_reserviert_fuer_dieses_mitglied_erlaubt():
    # 0301
    g = _make_gegenstand(zustand=GegenstandZustand.reserviert)
    gruende = prüfe_ausgabebedingungen(g, None, 0, False, True, True)
    assert gruende == []


def test_ausgabe_einweisung_fehlt():
    # 0301
    kat = _make_kategorie(einweisungspflichtig=True)
    g = _make_gegenstand(kategorie=kat)
    gruende = prüfe_ausgabebedingungen(g, None, 0, False, False, False)
    assert any("BR-08" in gr for gr in gruende)


def test_ausgabe_wartungsfaellig_nicht_verfuegbar():
    # 0301: wartungsfällig → BR-05
    g = _make_gegenstand(zustand=GegenstandZustand.wartungsfaellig)
    gruende = prüfe_ausgabebedingungen(g, None, 0, False, True, False)
    assert any("BR-05" in gr for gr in gruende)


# ─────────────────────────────────────────────
#  prüfe_verlaengerungsbedingungen  — 0303
# ─────────────────────────────────────────────


def test_verlaengerung_alle_bedingungen_ok():
    # 0303
    a = _make_ausleihe(rueckgabefrist=date(2026, 9, 15))
    gruende = prüfe_verlaengerungsbedingungen(a, HEUTE, False)
    assert gruende == []


def test_verlaengerung_bereits_verlaengert():
    # 0303
    import uuid
    a = Ausleihe(
        id=uuid.uuid4(),
        gegenstand_id=uuid.uuid4(),
        mitglied_id=uuid.uuid4(),
        ausgabe_datum=date(2026, 8, 1),
        rueckgabefrist=date(2026, 9, 15),
        kaution_betrag=20,
        verlaengert=True,
    )
    gruende = prüfe_verlaengerungsbedingungen(a, HEUTE, False)
    assert any("bereits_verlaengert" in gr for gr in gruende)


def test_verlaengerung_ueberfaellig():
    # 0303
    a = _make_ausleihe(rueckgabefrist=date(2026, 8, 20))
    gruende = prüfe_verlaengerungsbedingungen(a, HEUTE, False)
    assert any("ueberfaellig" in gr for gr in gruende)


def test_verlaengerung_offene_vormerkung():
    # 0303
    a = _make_ausleihe(rueckgabefrist=date(2026, 9, 15))
    gruende = prüfe_verlaengerungsbedingungen(a, HEUTE, True)
    assert any("vormerkung_offen" in gr for gr in gruende)
