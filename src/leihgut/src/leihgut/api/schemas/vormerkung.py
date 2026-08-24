"""Pydantic-Schemas für Vormerkungen (API-Schicht)."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class VormerkungAnlegen(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    mitglied_id: uuid.UUID = Field(alias="mitgliedId")
    kategorie_id: uuid.UUID = Field(alias="kategorieId")


class ReservierungInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    gegenstand_id: str = Field(alias="gegenstandId")
    reserviert_bis: str = Field(alias="reserviertBis")


class VormerkungAntwort(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    vormerkung_id: uuid.UUID = Field(alias="vormerkungId")
    mitglied_id: uuid.UUID = Field(alias="mitgliedId")
    kategorie_id: uuid.UUID = Field(alias="kategorieId")
    kategorie_name: str = Field(alias="kategorieName")
    eingangszeit: datetime
    position_in_schlange: int = Field(alias="positionInSchlange")
    reservierung: Optional[ReservierungInfo] = None
    hinweis: Optional[str] = None


class MitgliedVormerkungAntwort(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    vormerkung_id: uuid.UUID = Field(alias="vormerkungId")
    kategorie_id: uuid.UUID = Field(alias="kategorieId")
    kategorie_name: str = Field(alias="kategorieName")
    eingangszeit: datetime
    status: str
    position_in_schlange: int = Field(alias="positionInSchlange")
    reservierung: Optional[ReservierungInfo] = None
