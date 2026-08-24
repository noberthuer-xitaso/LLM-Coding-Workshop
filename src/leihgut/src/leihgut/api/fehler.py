"""Fehlerformat-Schemas und HTTP-Hilfsfunktionen."""

from typing import Any, Optional

from pydantic import BaseModel


class FehlerAntwort(BaseModel):
    """Einheitliches Fehlerformat gemäß Interface Contract."""

    fehler_code: str
    beschreibung: str
    kontext: Optional[dict[str, Any]] = None
