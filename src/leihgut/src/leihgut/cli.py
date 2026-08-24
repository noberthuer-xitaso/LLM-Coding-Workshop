"""Leihgut CLI — Typer-Anwendung für Wart-Aufgaben."""

import typer

app = typer.Typer(name="leihgut", help="Werkzeugverleih CLI")

kategorie_app = typer.Typer(help="Kategorien verwalten")
gegenstand_app = typer.Typer(help="Gegenstände verwalten")
einweisung_app = typer.Typer(help="Einweisungen verwalten")
wartung_app = typer.Typer(help="Wartung durchführen")
pruefprotokoll_app = typer.Typer(help="Prüfprotokolle erstellen")

app.add_typer(kategorie_app, name="kategorie")
app.add_typer(gegenstand_app, name="gegenstand")
app.add_typer(einweisung_app, name="einweisung")
app.add_typer(wartung_app, name="wartung")
app.add_typer(pruefprotokoll_app, name="pruefprotokoll")


if __name__ == "__main__":
    app()
