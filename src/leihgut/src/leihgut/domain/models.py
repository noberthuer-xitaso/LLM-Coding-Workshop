"""Domain-Modelle für Leihgut.

Alle Bezeichner folgen dem Glossar des PRD (Ubiquitous Language).
Deutsche Feldnamen im Code — kein Mapping zwischen Fachbegriff und Codebegriff.
"""

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


# ─────────────────────────────────────────────
#  Enumerationen
# ─────────────────────────────────────────────


class GegenstandZustand(str, Enum):
    verfuegbar = "verfügbar"
    ausgeliehen = "ausgeliehen"
    in_pruefung = "in_Prüfung"
    reserviert = "reserviert"
    wartungsfaellig = "wartungsfällig"
    ausgemustert = "ausgemustert"


class AusleiheStatus(str, Enum):
    aktiv = "aktiv"
    in_pruefung = "in_Prüfung"
    abgeschlossen = "abgeschlossen"


class PruefprotokollNachzustand(str, Enum):
    verfuegbar = "verfügbar"
    wartungsfaellig = "wartungsfällig"
    ausgemustert = "ausgemustert"
    verloren = "verloren"


class KautionsbewegungArt(str, Enum):
    hinterlegung = "hinterlegung"
    abzug = "abzug"
    freigabe = "freigabe"
    einbehaltung = "einbehaltung"


class VormerkungStatus(str, Enum):
    aktiv = "aktiv"
    storniert = "storniert"


class ReservierungStatus(str, Enum):
    aktiv = "aktiv"
    abgeholt = "abgeholt"
    verfallen = "verfallen"
    uebersprungen = "übersprungen"


class AuditTyp(str, Enum):
    zustandswechsel = "zustandswechsel"
    kautionsbewegung = "kautionsbewegung"


# ─────────────────────────────────────────────
#  Entitäten
# ─────────────────────────────────────────────


class Kategorie(SQLModel, table=True):
    """BR-01, BR-02: Bestimmt Leihdauer, Wartungsintervall, Einweisungspflicht."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)
    leihdauer_tage: int = Field(gt=0)
    wartungsintervall_ausleihen: int = Field(gt=0)
    einweisungspflichtig: bool = Field(default=False)

    gegenstaende: list["Gegenstand"] = Relationship(back_populates="kategorie")
    einweisungen: list["Einweisung"] = Relationship(back_populates="kategorie")
    vormerkungen: list["Vormerkung"] = Relationship(back_populates="kategorie")


class Gegenstand(SQLModel, table=True):
    """BR-01: Eindeutige Inventarnummer. BR-03: Wiederbeschaffungswert > 0."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    inventarnummer: str = Field(unique=True, index=True)
    kategorie_id: uuid.UUID = Field(foreign_key="kategorie.id")
    wiederbeschaffungswert_euro: int = Field(gt=0)
    zustand: GegenstandZustand = Field(default=GegenstandZustand.verfuegbar)
    nutzungszaehler: int = Field(default=0, ge=0)

    kategorie: Optional[Kategorie] = Relationship(back_populates="gegenstaende")
    ausleihen: list["Ausleihe"] = Relationship(back_populates="gegenstand")
    reservierungen: list["Reservierung"] = Relationship(back_populates="gegenstand")
    audit_eintraege: list["AuditEintrag"] = Relationship(back_populates="gegenstand")


class Mitglied(SQLModel, table=True):
    """BR-34/35: gesperrt ist abgeleitet, kein persistentes Feld."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str

    ausleihen: list["Ausleihe"] = Relationship(back_populates="mitglied")
    einweisungen: list["Einweisung"] = Relationship(back_populates="mitglied")
    vormerkungen: list["Vormerkung"] = Relationship(back_populates="mitglied")
    reservierungen: list["Reservierung"] = Relationship(back_populates="mitglied")


class Einweisung(SQLModel, table=True):
    """BR-08: Pflicht für einweisungspflichtige Kategorien."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    mitglied_id: uuid.UUID = Field(foreign_key="mitglied.id")
    kategorie_id: uuid.UUID = Field(foreign_key="kategorie.id")
    datum: date
    dokumentiert_von: str  # Wart-ID oder Name

    mitglied: Optional[Mitglied] = Relationship(back_populates="einweisungen")
    kategorie: Optional[Kategorie] = Relationship(back_populates="einweisungen")


class Ausleihe(SQLModel, table=True):
    """BR-09: Kaution hinterlegen, Rückgabefrist setzen."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    gegenstand_id: uuid.UUID = Field(foreign_key="gegenstand.id")
    mitglied_id: uuid.UUID = Field(foreign_key="mitglied.id")
    ausgabe_datum: date
    rueckgabefrist: date
    rueckgabe_datum: Optional[date] = Field(default=None)
    verlaengert: bool = Field(default=False)
    kaution_betrag: int  # BR-04: 20% des WBW, min 5, max 100
    status: AusleiheStatus = Field(default=AusleiheStatus.aktiv)
    thekendienst: Optional[str] = Field(default=None)
    auffaelligkeiten: Optional[str] = Field(default=None)

    gegenstand: Optional[Gegenstand] = Relationship(back_populates="ausleihen")
    mitglied: Optional[Mitglied] = Relationship(back_populates="ausleihen")
    pruefprotokoll: Optional["Pruefprotokoll"] = Relationship(back_populates="ausleihe")
    kautionsbewegungen: list["Kautionsbewegung"] = Relationship(back_populates="ausleihe")


class Pruefprotokoll(SQLModel, table=True):
    """BR-15: Schließt Ausleihe ab. BR-18: Nachzustand explizit."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ausleihe_id: uuid.UUID = Field(foreign_key="ausleihe.id", unique=True)
    wart_id: str
    erstellt_am: datetime
    kautionsabzug: int = Field(default=0, ge=0)  # BR-21: max = kaution_betrag
    nachzustand: PruefprotokollNachzustand
    begruendung: Optional[str] = Field(default=None)

    ausleihe: Optional[Ausleihe] = Relationship(back_populates="pruefprotokoll")


class Kautionsbewegung(SQLModel, table=True):
    """BR-22: Append-only. Hinterlegung, Abzug, Freigabe, Einbehaltung."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ausleihe_id: uuid.UUID = Field(foreign_key="ausleihe.id")
    art: KautionsbewegungArt
    betrag: int  # in ganzen Euro, immer positiv
    zeitstempel: datetime
    referenz_id: Optional[uuid.UUID] = Field(default=None)  # Ausleihe-ID oder Protokoll-ID

    ausleihe: Optional[Ausleihe] = Relationship(back_populates="kautionsbewegungen")


class Vormerkung(SQLModel, table=True):
    """BR-27..29: FIFO-Warteschlange pro Kategorie."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    mitglied_id: uuid.UUID = Field(foreign_key="mitglied.id")
    kategorie_id: uuid.UUID = Field(foreign_key="kategorie.id")
    eingangszeit: datetime
    status: VormerkungStatus = Field(default=VormerkungStatus.aktiv)

    mitglied: Optional[Mitglied] = Relationship(back_populates="vormerkungen")
    kategorie: Optional[Kategorie] = Relationship(back_populates="vormerkungen")
    reservierungen: list["Reservierung"] = Relationship(back_populates="vormerkung")


class Reservierung(SQLModel, table=True):
    """BR-30..31: 3 Kalendertage Verfall."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    gegenstand_id: uuid.UUID = Field(foreign_key="gegenstand.id")
    mitglied_id: uuid.UUID = Field(foreign_key="mitglied.id")
    vormerkung_id: uuid.UUID = Field(foreign_key="vormerkung.id")
    erstellt_am: date
    verfall_datum: date  # erstellt_am + 3 Tage
    status: ReservierungStatus = Field(default=ReservierungStatus.aktiv)

    gegenstand: Optional[Gegenstand] = Relationship(back_populates="reservierungen")
    mitglied: Optional[Mitglied] = Relationship(back_populates="reservierungen")
    vormerkung: Optional[Vormerkung] = Relationship(back_populates="reservierungen")


class AuditEintrag(SQLModel, table=True):
    """Append-only log für Zustandswechsel und Kautionsbewegungen."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    zeitstempel: datetime
    typ: AuditTyp
    # Für Zustandswechsel
    gegenstand_id: Optional[uuid.UUID] = Field(default=None, foreign_key="gegenstand.id")
    altzustand: Optional[str] = Field(default=None)
    neuzustand: Optional[str] = Field(default=None)
    # Für Kautionsbewegungen
    kautionsbewegung_art: Optional[str] = Field(default=None)
    betrag: Optional[int] = Field(default=None)
    # Gemeinsame Referenzen
    ausleihe_id: Optional[uuid.UUID] = Field(default=None)
    pruefprotokoll_id: Optional[uuid.UUID] = Field(default=None)

    gegenstand: Optional[Gegenstand] = Relationship(back_populates="audit_eintraege")
