"""Pydantic-Schemas für EPIC-0300: Ausleihe + Verlängerung.

Issue: 0301, 0302, 0303, 0304, 0801, 0802
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel


class AusleiheAnlegen(BaseModel):
    gegenstandId: str  # Inventarnummer
    mitgliedId: str
    ausgabedatum: Optional[date] = None


class AusleiheAntwort(BaseModel):
    ausleiheId: str
    gegenstandId: str  # Inventarnummer
    mitgliedId: str
    ausgabedatum: date
    rueckgabefrist: date
    kautionsbetrag: int
    verlaengert: bool
    status: str
    ueberfaellig: bool


class AusleiheAnlegenAntwort(BaseModel):
    ausleiheId: str
    gegenstandId: str  # Inventarnummer
    mitgliedId: str
    ausgabedatum: date
    rueckgabefrist: date
    kautionsbetrag: int
    gegenstandZustand: str
    leihdauerTage: int


class AusgabefaehigkeitAntwort(BaseModel):
    darfAusgegeben: bool
    ablehnungsgruende: list[str]


class SperrstatusAntwort(BaseModel):
    mitgliedId: str
    gesperrt: bool
    ueberfaelligeAusleihen: int
