"""Unit-Tests für Prüfprotokoll-Regeln (EPIC-0400, EPIC-0500).

Issue: # 0401, # 0402, # 0403, # 0502, # 0503
Testet reine Domänenlogik — keine Datenbankzugriffe.
"""

import pytest

from leihgut.domain.regeln import bestimme_effektiven_nachzustand, prüfe_kautionsabzug


# ─────────────────────────────────────────────
#  BR-21: Kautionsabzug-Obergrenze
# ─────────────────────────────────────────────


def test_kautionsabzug_erlaubt():
    """BR-21: Abzug kleiner als Kaution → kein Fehler."""
    assert prüfe_kautionsabzug(10, 40) == []


def test_kautionsabzug_gleich_kaution_erlaubt():
    """BR-21: Abzug gleich Kaution → erlaubt."""
    assert prüfe_kautionsabzug(40, 40) == []


def test_kautionsabzug_null_erlaubt():
    """BR-21: Kein Abzug → immer erlaubt."""
    assert prüfe_kautionsabzug(0, 40) == []


def test_kautionsabzug_zu_hoch():
    """BR-21: Abzug größer als Kaution → Fehler mit BR-21-Referenz."""
    result = prüfe_kautionsabzug(50, 40)
    assert len(result) == 1
    assert "BR-21" in result[0]
    assert "50" in result[0]
    assert "40" in result[0]


# ─────────────────────────────────────────────
#  BR-19/24: Effektiver Nachzustand
# ─────────────────────────────────────────────


def test_nachzustand_verfuegbar_bleibt_verfuegbar():
    """Ohne Wartungsintervall-Überschreitung bleibt der Zustand verfügbar."""
    result = bestimme_effektiven_nachzustand("verfügbar", nutzungszaehler_neu=5, wartungsintervall=10)
    assert result == "verfügbar"


def test_nachzustand_wartungsfaellig_durch_intervall():
    """BR-24: Nutzungszähler = Wartungsintervall → effektiv wartungsfällig."""
    result = bestimme_effektiven_nachzustand("verfügbar", nutzungszaehler_neu=9, wartungsintervall=9)
    assert result == "wartungsfällig"


def test_nachzustand_wartungsfaellig_ueberschritten():
    """BR-24: Nutzungszähler > Intervall → wartungsfällig (überschreibt Eingabe)."""
    result = bestimme_effektiven_nachzustand("verfügbar", nutzungszaehler_neu=10, wartungsintervall=10)
    assert result == "wartungsfällig"


def test_nachzustand_wartungsfaellig_mit_intervall_9_10():
    """BR-24: nutzungszaehler=9, intervall=10 → wartungsfällig (Spec-Beispiel)."""
    result = bestimme_effektiven_nachzustand("verfügbar", nutzungszaehler_neu=9, wartungsintervall=10)
    # 9 < 10 → kein Wartungsintervall ausgelöst
    assert result == "verfügbar"


def test_nachzustand_wartungsfaellig_exakt_10():
    """BR-24: nutzungszaehler=10, intervall=10 → wartungsfällig."""
    result = bestimme_effektiven_nachzustand("verfügbar", nutzungszaehler_neu=10, wartungsintervall=10)
    assert result == "wartungsfällig"


def test_nachzustand_verloren_ergibt_ausgemustert():
    """BR-19: verloren → effektiv ausgemustert (absolute Priorität)."""
    result = bestimme_effektiven_nachzustand("verloren", nutzungszaehler_neu=1, wartungsintervall=10)
    assert result == "ausgemustert"


def test_nachzustand_verloren_ueberschreibt_wartungsintervall():
    """BR-19: verloren geht vor Wartungsintervall."""
    result = bestimme_effektiven_nachzustand("verloren", nutzungszaehler_neu=10, wartungsintervall=10)
    assert result == "ausgemustert"


def test_nachzustand_ausgemustert_eingabe():
    """Explizit ausgemustert ohne Wartungsintervall bleibt ausgemustert."""
    result = bestimme_effektiven_nachzustand("ausgemustert", nutzungszaehler_neu=1, wartungsintervall=10)
    assert result == "ausgemustert"


def test_nachzustand_wartungsfaellig_ueberschreibt_ausgemustert():
    """BR-24: Wartungsintervall überschreibt auch explizit ausgemustert."""
    result = bestimme_effektiven_nachzustand("ausgemustert", nutzungszaehler_neu=10, wartungsintervall=10)
    assert result == "wartungsfällig"
