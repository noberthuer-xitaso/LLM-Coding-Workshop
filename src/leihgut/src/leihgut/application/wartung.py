"""Application Use Cases für EPIC-0600: Wartung und Ausmusterung.

Issue: # 0603, # 0604
IOSP: reine Integration — orchestriert DB-Zugriff, keine eigene Berechnungslogik.
"""

from datetime import date, datetime

from sqlmodel import Session, select

from leihgut.application.audit import erfasse_zustandswechsel
from leihgut.application.pruefprotokoll import versuche_reservierung_anlegen
from leihgut.domain.models import Gegenstand, GegenstandZustand
from leihgut.infrastructure.datum import SystemDatumsQuelle

# ─────────────────────────────────────────────
#  Globale DatumsQuelle (überschreibbar in Tests)
# ─────────────────────────────────────────────

_datumsquelle = SystemDatumsQuelle()


def set_datumsquelle(dq) -> None:
    global _datumsquelle
    _datumsquelle = dq


# ─────────────────────────────────────────────
#  Anwendungsausnahmen
# ─────────────────────────────────────────────


class GegenstandNichtGefunden(Exception):
    def __init__(self, inventarnummer: str) -> None:
        self.inventarnummer = inventarnummer


class GegenstandNichtWartungsfaellig(Exception):
    def __init__(self, inventarnummer: str, zustand: str) -> None:
        self.inventarnummer = inventarnummer
        self.zustand = zustand


# ─────────────────────────────────────────────
#  UC-0603: Wartung abschließen
# ─────────────────────────────────────────────


def wartung_abschliessen(session: Session, inventarnummer: str, heute: date) -> dict:
    """BR-25: Nutzungszähler = 0, Zustand verfügbar oder reserviert (BR-30)."""
    gegenstand = session.exec(
        select(Gegenstand).where(Gegenstand.inventarnummer == inventarnummer)
    ).first()

    if gegenstand is None:
        raise GegenstandNichtGefunden(inventarnummer)

    if gegenstand.zustand != GegenstandZustand.wartungsfaellig:
        raise GegenstandNichtWartungsfaellig(inventarnummer, gegenstand.zustand.value)

    altzustand = gegenstand.zustand.value
    jetzt = datetime.now()

    # BR-25: Nutzungszähler zurücksetzen
    gegenstand.nutzungszaehler = 0

    # BR-30 analog: Offene Vormerkung prüfen
    gegenstand.zustand = GegenstandZustand.verfuegbar
    session.add(gegenstand)
    reserviert_fuer = versuche_reservierung_anlegen(session, gegenstand, heute)

    session.commit()
    session.refresh(gegenstand)

    erfasse_zustandswechsel(
        session,
        gegenstand.id,
        altzustand,
        gegenstand.zustand.value,
        jetzt,
    )

    return {
        "inventarnummer": gegenstand.inventarnummer,
        "zustand": gegenstand.zustand.value,
        "nutzungszaehler": gegenstand.nutzungszaehler,
        "reserviertFuer": str(reserviert_fuer) if reserviert_fuer else None,
    }
