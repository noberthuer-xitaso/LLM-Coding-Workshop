"""API-Schemas für den Katalog (EPIC-0100).

Request-Schemas: camelCase-Aliasse, snake_case Python-Feldnamen.
Response-Schemas: camelCase-Feldnamen direkt (kein Alias-Mapping nötig).
"""

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────
#  Kategorie
# ─────────────────────────────────────────────


class KategorieAnlegenAnfrage(BaseModel):
    """Request für POST /kategorien und PUT /kategorien/{id}."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    leihdauer_tage: int = Field(alias="leihdauerTage", gt=0)
    wartungsintervall_ausleihen: int = Field(alias="wartungsintervallAusleihen", gt=0)
    einweisungspflichtig: bool = False


class KategorieAntwort(BaseModel):
    """Response für alle Kategorie-Endpunkte."""

    kategorieId: str
    name: str
    leihdauerTage: int
    wartungsintervallAusleihen: int
    einweisungspflichtig: bool


# ─────────────────────────────────────────────
#  Gegenstand
# ─────────────────────────────────────────────


class GegenstandAnlegenAnfrage(BaseModel):
    """Request für POST /gegenstaende."""

    model_config = ConfigDict(populate_by_name=True)

    inventarnummer: str
    kategorie_id: uuid.UUID = Field(alias="kategorieId")
    wiederbeschaffungswert: int = Field(gt=0)


class GegenstandAktualisierenAnfrage(BaseModel):
    """Request für PATCH /gegenstaende/{inventarnummer}."""

    wiederbeschaffungswert: Optional[int] = Field(default=None, gt=0)


class GegenstandAntwort(BaseModel):
    """Response für alle Gegenstand-Endpunkte."""

    gegenstandId: str
    inventarnummer: str
    kategorieId: str
    kategorieName: str
    wiederbeschaffungswert: int
    kaution: int
    zustand: str
    nutzungszaehler: int
