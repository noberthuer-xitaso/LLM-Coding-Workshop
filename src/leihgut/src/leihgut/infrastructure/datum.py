"""DatumsQuelle — Strategy Pattern für testbare Zeitabhängigkeiten.

TC-07: Das aktuelle Datum wird über eine injizierbare Schnittstelle geliefert.
Im Produktionsbetrieb: SystemDatumsQuelle.
In Tests: FixesDatum mit konfigurierbarem Wert.
"""

from datetime import date
from typing import Protocol


class DatumsQuelle(Protocol):
    """Port: Liefert das aktuelle Datum."""

    def heute(self) -> date: ...


class SystemDatumsQuelle:
    """Adapter: Liest das Datum von der Systemuhr."""

    def heute(self) -> date:
        return date.today()


class FixesDatum:
    """Test-Adapter: Gibt immer denselben Fixwert zurück."""

    def __init__(self, datum: date) -> None:
        self._datum = datum

    def heute(self) -> date:
        return self._datum
