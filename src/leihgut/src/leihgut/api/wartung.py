"""API-Router für EPIC-0600: Wartung und Ausmusterung.

Issue: # 0603, # 0604
HTTP-Routing, Serialisierung und Rollenkontrolle gemäß Interface Contract.

CLI-Äquivalent (nur dokumentiert, nicht implementiert):
  leihgut wartung abschliessen --gegenstand INV-00042
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session

from leihgut.application import wartung as wartung_app
from leihgut.application.wartung import GegenstandNichtGefunden, GegenstandNichtWartungsfaellig
from leihgut.infrastructure.datenbank import get_session

router = APIRouter()

_ROLLEN_WART = {"wart"}


def _pruefe_rolle(rolle: str) -> None:
    if rolle not in _ROLLEN_WART:
        raise HTTPException(
            status_code=403,
            detail={
                "fehler_code": "ROLLE_UNZULAESSIG",
                "beschreibung": f"Rolle '{rolle}' hat keine Berechtigung.",
            },
        )


# ─────────────────────────────────────────────
#  Story 0603: Wartung abschließen
# ─────────────────────────────────────────────


@router.post("/gegenstaende/{inventarnummer}/wartung-abschliessen")
def wartung_abschliessen(
    inventarnummer: str,
    x_role: str = Header(default=""),
    session: Session = Depends(get_session),
) -> dict:
    """POST /gegenstaende/{inventarnummer}/wartung-abschliessen — # 0603"""
    _pruefe_rolle(x_role)
    heute = wartung_app._datumsquelle.heute()

    try:
        return wartung_app.wartung_abschliessen(session, inventarnummer, heute)
    except GegenstandNichtGefunden as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "fehler_code": "GEGENSTAND_NICHT_GEFUNDEN",
                "beschreibung": f"Gegenstand '{exc.inventarnummer}' nicht gefunden.",
            },
        ) from exc
    except GegenstandNichtWartungsfaellig as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "fehler_code": "GEGENSTAND_NICHT_WARTUNGSFAELLIG",
                "beschreibung": (
                    f"Gegenstand '{exc.inventarnummer}' ist nicht wartungsfällig "
                    f"(aktueller Zustand: '{exc.zustand}')."
                ),
            },
        ) from exc
