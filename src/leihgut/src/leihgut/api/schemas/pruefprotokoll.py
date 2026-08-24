"""Pydantic-Schemas für EPIC-0400: Rückgabe & Prüfung, EPIC-0500: Kaution.

Issue: # 0401, # 0402, # 0403, # 0502, # 0503, # 0504
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from leihgut.domain.models import PruefprotokollNachzustand


class RueckgabeAnfrage(BaseModel):
    auffaelligkeiten: Optional[str] = Field(default=None, max_length=1000)


class RueckgabeAntwort(BaseModel):
    ausleiheId: str
    gegenstandId: str  # Inventarnummer
    zustand: str
    zeitstempelRueckgabe: datetime


class PruefprotokollAnfrage(BaseModel):
    nachzustand: PruefprotokollNachzustand
    kautionsabzug: int = Field(default=0, ge=0)
    begruendung: Optional[str] = Field(default=None)


class PruefprotokollAntwort(BaseModel):
    pruefprotokollId: str
    ausleiheId: str
    gegenstandId: str  # Inventarnummer
    wartId: str
    zeitstempel: datetime
    nachzustandEingabe: str
    nachzustandEffektiv: str
    kautionsabzug: int
    kautionFreigegeben: int
    begruendung: Optional[str]
    reserviertFuer: Optional[str]
    vorherigePruefprotokoll: Optional[str]


class KautionsbewegungAntwort(BaseModel):
    id: str
    art: str
    betrag: int
    zeitstempel: datetime
    ausleiheId: str
    pruefprotokollId: Optional[str]
