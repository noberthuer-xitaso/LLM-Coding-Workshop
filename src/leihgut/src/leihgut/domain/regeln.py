"""Geschäftsregeln der Domain — reine Logik (IOSP: Operations).

Keine Datenbankzugriffe, keine Seiteneffekte.
Jede Funktion ist eine reine Berechnung oder Prüfung.
"""

from decimal import ROUND_HALF_UP, Decimal

from leihgut.domain.models import (
    Ausleihe,
    AusleiheStatus,
    Gegenstand,
    GegenstandZustand,
)


# ─────────────────────────────────────────────
#  BR-04: Kautionsberechnung
# ─────────────────────────────────────────────


def berechne_kaution(wiederbeschaffungswert_euro: int) -> int:
    """BR-04: 20% des WBW, kaufm. gerundet, min 5, max 100 Euro.

    Python's round() verwendet Banker's Rounding (HALF_EVEN).
    Decimal mit ROUND_HALF_UP liefert kaufmännisches Runden.
    """
    raw = Decimal(str(wiederbeschaffungswert_euro)) * Decimal("0.20")
    gerundet = int(raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(5, min(100, gerundet))


# ─────────────────────────────────────────────
#  BR-34/35: Mitgliedersperre
# ─────────────────────────────────────────────


def ist_mitglied_gesperrt(ausleihen: list[Ausleihe], heute: object) -> bool:
    """BR-34/35: Gesperrt wenn mind. eine Ausleihe überfällig.

    Überfällig = Rückgabefrist < heute AND nicht zurückgegeben (BR-35).
    heute ist ein date-Objekt (über DatumsQuelle injiziert).
    """
    return any(
        a.rueckgabefrist < heute
        and a.rueckgabe_datum is None
        and a.status == AusleiheStatus.aktiv
        for a in ausleihen
    )


# ─────────────────────────────────────────────
#  BR-05..08: Ausgabebedingungen
# ─────────────────────────────────────────────


def prüfe_ausgabebedingungen(
    gegenstand: Gegenstand,
    mitglied_id: object,
    aktive_ausleihen_count: int,
    ist_gesperrt: bool,
    hat_einweisung: bool,
    reserviert_fuer_mitglied: bool,
) -> list[str]:
    """BR-05..08: Gibt Liste der Ablehnungsgründe zurück. Leer = erlaubt.

    BR-05: Zustand verfügbar oder reserviert für dieses Mitglied.
    BR-06: Max. 3 aktive Ausleihen.
    BR-07: Nicht gesperrt.
    BR-08: Einweisung vorhanden wenn einweisungspflichtig.
    """
    gruende: list[str] = []

    erlaubte_zustaende = {GegenstandZustand.verfuegbar}
    if reserviert_fuer_mitglied:
        erlaubte_zustaende.add(GegenstandZustand.reserviert)

    if gegenstand.zustand not in erlaubte_zustaende:
        gruende.append("BR-05: Gegenstand nicht verfügbar")

    if aktive_ausleihen_count >= 3:
        gruende.append("BR-06: Ausleihlimit (3) erreicht")

    if ist_gesperrt:
        gruende.append("BR-07: Mitglied gesperrt")

    if gegenstand.kategorie and gegenstand.kategorie.einweisungspflichtig and not hat_einweisung:
        gruende.append("BR-08: Einweisung fehlt")

    return gruende


# ─────────────────────────────────────────────
#  BR-10/11: Verlängerungsbedingungen
# ─────────────────────────────────────────────


def prüfe_verlaengerungsbedingungen(
    ausleihe: Ausleihe,
    heute: object,
    hat_offene_vormerkung: bool,
) -> list[str]:
    """BR-10/11: Verlängerung genau einmal, nicht bei Überfälligkeit oder Vormerkung."""
    gruende: list[str] = []

    if ausleihe.verlaengert:
        gruende.append("BR-10: bereits_verlaengert")

    if ausleihe.rueckgabefrist < heute:
        gruende.append("BR-11: ueberfaellig")

    if hat_offene_vormerkung:
        gruende.append("BR-11: vormerkung_offen")

    return gruende


# ─────────────────────────────────────────────
#  BR-21: Kautionsabzug-Obergrenze
# ─────────────────────────────────────────────


def prüfe_kautionsabzug(abzug: int, hinterlegte_kaution: int) -> list[str]:
    """BR-21: Abzug darf hinterlegte Kaution nicht übersteigen."""
    if abzug > hinterlegte_kaution:
        return [f"BR-21: Abzug {abzug} > hinterlegte Kaution {hinterlegte_kaution}"]
    return []
