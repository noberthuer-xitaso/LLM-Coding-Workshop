"""FastAPI-Anwendungsinstanz für Leihgut."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
