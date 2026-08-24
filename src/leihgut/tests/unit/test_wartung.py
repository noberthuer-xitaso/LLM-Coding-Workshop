"""Unit-Tests für EPIC-0600: Wartung und Ausmusterung.

Issue: # 0601, # 0602
Testet reine Domänenlogik — keine Datenbankzugriffe.
"""

import uuid

import pytest

from leihgut.domain.models import Gegenstand, GegenstandZustand, Kategorie
from leihgut.domain.regeln import bestimme_effektiven_nachzustand, prüfe_ausgabebedingungen


# ─────────────────────────────────────────────
#  Story 0601: Nutzungszähler → Wartungsfälligkeit
# ─────────────────────────────────────────────


def test_nutzungszaehler_gleich_intervall_ergibt_wartungsfaellig():
    """BR-24: Zähler = Intervall → 'wartungsfällig'. # 0601 # 0602"""
    result = bestimme_effektiven_nachzustand(
        "verfügbar", nutzungszaehler_neu=10, wartungsintervall=10
    )
    assert result == "wartungsfällig"


def test_nutzungszaehler_unter_intervall_bleibt_verfuegbar():
    """BR-24: Zähler < Intervall → Eingabezustand bleibt erhalten. # 0601"""
    result = bestimme_effektiven_nachzustand(
        "verfügbar", nutzungszaehler_neu=9, wartungsintervall=10
    )
    assert result == "verfügbar"


def test_nutzungszaehler_ueber_intervall_ergibt_wartungsfaellig():
    """BR-24: Zähler > Intervall → 'wartungsfällig' (Überlauf-Fall). # 0601"""
    result = bestimme_effektiven_nachzustand(
        "verfügbar", nutzungszaehler_neu=15, wartungsintervall=10
    )
    assert result == "wartungsfällig"


def test_wartungsfaelligkeit_hat_prioritaet_ueber_nachzustand():
    """BR-24: Intervallüberschreitung überschreibt auch 'ausgemustert'-Eingabe — außer 'verloren'. # 0601 # 0602"""
    result = bestimme_effektiven_nachzustand(
        "ausgemustert", nutzungszaehler_neu=10, wartungsintervall=10
    )
    assert result == "wartungsfällig"


def test_verloren_hat_absolute_prioritaet():
    """BR-19: 'verloren' → 'ausgemustert' — auch wenn Intervall erreicht. # 0601"""
    result = bestimme_effektiven_nachzustand(
        "verloren", nutzungszaehler_neu=10, wartungsintervall=10
    )
    assert result == "ausgemustert"


# ─────────────────────────────────────────────
#  Story 0602: Wartungsfälliger Gegenstand darf nicht ausgeliehen werden
# ─────────────────────────────────────────────


def _make_gegenstand(zustand: GegenstandZustand, einweisungspflichtig: bool = False) -> Gegenstand:
    kategorie = Kategorie(
        name="Test",
        leihdauer_tage=14,
        wartungsintervall_ausleihen=10,
        einweisungspflichtig=einweisungspflichtig,
    )
    g = Gegenstand(
        inventarnummer="INV-001",
        kategorie_id=uuid.uuid4(),
        wiederbeschaffungswert_euro=100,
        zustand=zustand,
    )
    object.__setattr__(g, "kategorie", kategorie)
    return g


def test_wartungsfaellig_darf_nicht_ausgeliehen_werden():
    """BR-05: Wartungsfälliger Gegenstand → Ausgabe abgelehnt. # 0602"""
    g = _make_gegenstand(GegenstandZustand.wartungsfaellig)
    gruende = prüfe_ausgabebedingungen(
        gegenstand=g,
        mitglied_id=uuid.uuid4(),
        aktive_ausleihen_count=0,
        ist_gesperrt=False,
        hat_einweisung=True,
        reserviert_fuer_mitglied=False,
    )
    assert any("BR-05" in g for g in gruende)


def test_verfuegbar_darf_ausgeliehen_werden():
    """BR-05: Verfügbarer Gegenstand → Ausgabe erlaubt. # 0602"""
    g = _make_gegenstand(GegenstandZustand.verfuegbar)
    gruende = prüfe_ausgabebedingungen(
        gegenstand=g,
        mitglied_id=uuid.uuid4(),
        aktive_ausleihen_count=0,
        ist_gesperrt=False,
        hat_einweisung=True,
        reserviert_fuer_mitglied=False,
    )
    assert gruende == []


def test_ausgeliehen_darf_nicht_nochmals_ausgeliehen_werden():
    """BR-05: Ausgeliehener Gegenstand → Ausgabe abgelehnt. # 0602"""
    g = _make_gegenstand(GegenstandZustand.ausgeliehen)
    gruende = prüfe_ausgabebedingungen(
        gegenstand=g,
        mitglied_id=uuid.uuid4(),
        aktive_ausleihen_count=0,
        ist_gesperrt=False,
        hat_einweisung=True,
        reserviert_fuer_mitglied=False,
    )
    assert any("BR-05" in gr for gr in gruende)
