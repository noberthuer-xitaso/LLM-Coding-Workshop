"""Pydantic-Schemas für Einweisungen und Mitglieder (API-Schicht)."""

import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MitgliedAnlegen(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MitgliedAntwort(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mitglied_id: uuid.UUID = Field(alias="mitgliedId")
    name: str

    @classmethod
    def from_mitglied(cls, m):
        return cls(mitgliedId=m.id, name=m.name)


class EinweisungAnlegen(BaseModel):
    mitglied_id: uuid.UUID = Field(alias="mitgliedId")
    kategorie_id: uuid.UUID = Field(alias="kategorieId")
    dokumentiert_von: Optional[str] = Field(default="wart", alias="dokumentiertVon")

    model_config = ConfigDict(populate_by_name=True)


class EinweisungAntwort(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    einweisung_id: uuid.UUID = Field(alias="einweisungId")
    mitglied_id: uuid.UUID = Field(alias="mitgliedId")
    kategorie_id: uuid.UUID = Field(alias="kategorieId")
    kategorie_name: str = Field(alias="kategorieName")
    datum: date
    dokumentiert_von: str = Field(alias="dokumentiertVon")

    @classmethod
    def from_einweisung(cls, e, kategorie_name: str):
        return cls(
            einweisungId=e.id,
            mitgliedId=e.mitglied_id,
            kategorieId=e.kategorie_id,
            kategorieName=kategorie_name,
            datum=e.datum,
            dokumentiertVon=e.dokumentiert_von,
        )
