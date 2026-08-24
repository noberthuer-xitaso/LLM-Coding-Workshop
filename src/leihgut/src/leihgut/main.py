"""FastAPI-Anwendungsinstanz für Leihgut."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from leihgut.api import audit as audit_router
from leihgut.api import einweisung as einweisung_router
from leihgut.api import katalog as katalog_router
from leihgut.infrastructure.datenbank import erstelle_tabellen


@asynccontextmanager
async def lifespan(application: FastAPI):
    erstelle_tabellen()
    yield


app = FastAPI(
    title="Leihgut — Werkzeugverleih",
    description="REST-API für die Bibliothek der Dinge",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(katalog_router.router)
app.include_router(audit_router.router)
app.include_router(einweisung_router.router)


@app.exception_handler(HTTPException)
async def http_fehler_handler(request, exc: HTTPException) -> JSONResponse:
    """Gibt dict-Details direkt zurück (kein FastAPI-Envelope)."""
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "fehler_code": str(exc.status_code),
            "beschreibung": str(exc.detail),
            "kontext": {},
        },
    )


@app.exception_handler(RequestValidationError)
async def validierungsfehler_handler(request, exc: RequestValidationError) -> JSONResponse:
    """Wandelt 422-Validierungsfehler in 400 EINGABE_UNGUELTIG um."""
    return JSONResponse(
        status_code=400,
        content={
            "fehler_code": "EINGABE_UNGUELTIG",
            "beschreibung": "Ungültige Eingabedaten.",
            "kontext": {"details": exc.errors()},
        },
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
