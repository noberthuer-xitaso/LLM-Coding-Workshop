"""Application Use Cases für Vormerkungen und Reservierungen.

Issues: 0701, 0702, 0703, 0704, 0705
IOSP: reine Integration — orchestriert DB und Domänenregeln, keine eigene Logik.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from leihgut.domain.models import (
    Ausleihe,
    AusleiheStatus,
    Gegenstand,
    GegenstandZustand,
    Kategorie,
    Mitglied,
    Reservierung,
    ReservierungStatus,
    Vormerkung,
    VormerkungStatus,
)
from leihgut.domain.regeln import ist_mitglied_gesperrt
from leihgut.application.audit import erfasse_zustandswechsel
from leihgut.infrastructure.datum import SystemDatumsQuelle

_datumsquelle = SystemDatumsQuelle()


def set_datumsquelle(dq) -> None:
    global _datumsquelle
    _datumsquelle = dq


# ─────────────────────────────────────────────
#  Exceptions
# ─────────────────────────────────────────────


class VormerkungBereitsVorhanden(Exception):
    pass


class VormerkungNichtGefunden(Exception):
    pass


class VormerkungBereitsStorniert(Exception):
    pass


class KategorieNichtGefunden(Exception):
    pass


class MitgliedNichtGefunden(Exception):
    pass


# ─────────────────────────────────────────────
#  Hilfsfunktionen
# ─────────────────────────────────────────────


def _ist_gesperrt(session: Session, mitglied_id: uuid.UUID, heute: date) -> bool:
    aktive = session.exec(
        select(Ausleihe).where(
            Ausleihe.mitglied_id == mitglied_id,
            Ausleihe.status == AusleiheStatus.aktiv,
        )
    ).all()
    return ist_mitglied_gesperrt(list(aktive), heute)


def prüfe_reservierungsverfall(session: Session, heute: date) -> None:
    """BR-31: Setzt verfallene Reservierungen inaktiv und löst Folge-Reservierungen aus."""
    verfallene = session.exec(
        select(Reservierung).where(
            Reservierung.status == ReservierungStatus.aktiv,
            Reservierung.verfall_datum < heute,
        )
    ).all()

    for res in verfallene:
        res.status = ReservierungStatus.verfallen
        session.add(res)

        gegenstand = session.get(Gegenstand, res.gegenstand_id)
        if not gegenstand:
            continue

        altzustand = gegenstand.zustand.value
        # Versuche nächste Vormerkung
        naechste = _naechste_nicht_gesperrte_vormerkung(
            session, gegenstand.kategorie_id, heute
        )
        if naechste:
            neue_res = Reservierung(
                gegenstand_id=gegenstand.id,
                mitglied_id=naechste.mitglied_id,
                vormerkung_id=naechste.id,
                erstellt_am=heute,
                verfall_datum=heute + timedelta(days=3),
            )
            session.add(neue_res)
            naechste.status = VormerkungStatus.storniert
            session.add(naechste)
            gegenstand.zustand = GegenstandZustand.reserviert
        else:
            gegenstand.zustand = GegenstandZustand.verfuegbar

        session.add(gegenstand)
        erfasse_zustandswechsel(
            session,
            gegenstand_id=gegenstand.id,
            altzustand=altzustand,
            neuzustand=gegenstand.zustand.value,
            zeitstempel=datetime.now(timezone.utc),
        )

    session.commit()


def _naechste_nicht_gesperrte_vormerkung(
    session: Session, kategorie_id: uuid.UUID, heute: date
) -> Optional[Vormerkung]:
    """FIFO: Erste aktive, nicht-gesperrte Vormerkung in der Kategorie."""
    stmt = (
        select(Vormerkung)
        .where(
            Vormerkung.kategorie_id == kategorie_id,
            Vormerkung.status == VormerkungStatus.aktiv,
        )
        .order_by(Vormerkung.eingangszeit)
    )
    for vm in session.exec(stmt).all():
        if not _ist_gesperrt(session, vm.mitglied_id, heute):
            return vm
    return None


# ─────────────────────────────────────────────
#  Story 0701: Vormerkung anlegen
# ─────────────────────────────────────────────


def vormerkung_anlegen(
    session: Session,
    mitglied_id: uuid.UUID,
    kategorie_id: uuid.UUID,
    heute: date,
) -> dict:
    """BR-27..30, BR-33: Platz in Warteschlange anlegen."""
    mitglied = session.get(Mitglied, mitglied_id)
    if not mitglied:
        raise MitgliedNichtGefunden(str(mitglied_id))

    kategorie = session.get(Kategorie, kategorie_id)
    if not kategorie:
        raise KategorieNichtGefunden(str(kategorie_id))

    # BR-28: Einmaligkeit je Kategorie
    doppelt = session.exec(
        select(Vormerkung).where(
            Vormerkung.mitglied_id == mitglied_id,
            Vormerkung.kategorie_id == kategorie_id,
            Vormerkung.status == VormerkungStatus.aktiv,
        )
    ).first()
    if doppelt:
        raise VormerkungBereitsVorhanden()

    # Verfallene Reservierungen prüfen
    prüfe_reservierungsverfall(session, heute)

    # Vormerkung anlegen (BR-29 FIFO via eingangszeit)
    eingangszeit = datetime.now(timezone.utc)
    vm = Vormerkung(
        mitglied_id=mitglied_id,
        kategorie_id=kategorie_id,
        eingangszeit=eingangszeit,
    )
    session.add(vm)
    session.flush()  # ID erzeugen

    # Position in Queue
    position = session.exec(
        select(Vormerkung).where(
            Vormerkung.kategorie_id == kategorie_id,
            Vormerkung.status == VormerkungStatus.aktiv,
        )
    ).all()
    pos = len([v for v in position if v.eingangszeit <= eingangszeit])

    # BR-33: gesperrtes Mitglied darf vormerken, erhält aber keine Reservierung
    gesperrt = _ist_gesperrt(session, mitglied_id, heute)

    reservierung_info = None
    hinweis = None

    if not gesperrt:
        # Sofort-Reservierung wenn verfügbarer Gegenstand (BR-30)
        gegenstand = session.exec(
            select(Gegenstand).where(
                Gegenstand.kategorie_id == kategorie_id,
                Gegenstand.zustand == GegenstandZustand.verfuegbar,
            )
        ).first()
        if gegenstand:
            altzustand = gegenstand.zustand.value
            verfall = heute + timedelta(days=3)
            res = Reservierung(
                gegenstand_id=gegenstand.id,
                mitglied_id=mitglied_id,
                vormerkung_id=vm.id,
                erstellt_am=heute,
                verfall_datum=verfall,
            )
            session.add(res)
            vm.status = VormerkungStatus.storniert  # eingelöst
            gegenstand.zustand = GegenstandZustand.reserviert
            session.add(gegenstand)
            erfasse_zustandswechsel(
                session,
                gegenstand_id=gegenstand.id,
                altzustand=altzustand,
                neuzustand=GegenstandZustand.reserviert.value,
                zeitstempel=datetime.now(timezone.utc),
            )
            reservierung_info = {
                "gegenstandId": gegenstand.inventarnummer,
                "reserviertBis": verfall.isoformat(),
            }
            hinweis = f"Gegenstand sofort reserviert. Abholung bis {verfall.isoformat()}."
    else:
        hinweis = (
            "Ihr Konto ist gesperrt. Die Vormerkung wird registriert, "
            "eine entstehende Reservierung wird jedoch übersprungen. "
            "Ihr Platz in der Warteschlange bleibt erhalten."
        )

    session.commit()
    session.refresh(vm)

    return {
        "vormerkungId": vm.id,
        "mitgliedId": mitglied_id,
        "kategorieId": kategorie_id,
        "kategorieName": kategorie.name,
        "eingangszeit": eingangszeit,
        "positionInSchlange": pos,
        "reservierung": reservierung_info,
        "hinweis": hinweis,
    }


# ─────────────────────────────────────────────
#  Story 0702: Vormerkung stornieren
# ─────────────────────────────────────────────


def vormerkung_stornieren(
    session: Session, vormerkung_id: uuid.UUID, heute: date
) -> None:
    """Story 0702: Storniert eine Vormerkung. Löst ggf. Reservierung auf."""
    vm = session.get(Vormerkung, vormerkung_id)
    if not vm:
        raise VormerkungNichtGefunden(str(vormerkung_id))
    if vm.status == VormerkungStatus.storniert:
        raise VormerkungBereitsStorniert()

    vm.status = VormerkungStatus.storniert
    session.add(vm)

    # Aktive Reservierung zu dieser Vormerkung aufheben
    res = session.exec(
        select(Reservierung).where(
            Reservierung.vormerkung_id == vormerkung_id,
            Reservierung.status == ReservierungStatus.aktiv,
        )
    ).first()
    if res:
        res.status = ReservierungStatus.verfallen
        session.add(res)

        gegenstand = session.get(Gegenstand, res.gegenstand_id)
        if gegenstand:
            altzustand = gegenstand.zustand.value
            # Nächste Vormerkung bedienen
            naechste = _naechste_nicht_gesperrte_vormerkung(
                session, gegenstand.kategorie_id, heute
            )
            if naechste:
                neue_res = Reservierung(
                    gegenstand_id=gegenstand.id,
                    mitglied_id=naechste.mitglied_id,
                    vormerkung_id=naechste.id,
                    erstellt_am=heute,
                    verfall_datum=heute + timedelta(days=3),
                )
                session.add(neue_res)
                naechste.status = VormerkungStatus.storniert
                session.add(naechste)
                gegenstand.zustand = GegenstandZustand.reserviert
            else:
                gegenstand.zustand = GegenstandZustand.verfuegbar
            session.add(gegenstand)
            erfasse_zustandswechsel(
                session,
                gegenstand_id=gegenstand.id,
                altzustand=altzustand,
                neuzustand=gegenstand.zustand.value,
                zeitstempel=datetime.now(timezone.utc),
            )

    session.commit()


# ─────────────────────────────────────────────
#  Story 0705: Eigene Vormerkungen abfragen
# ─────────────────────────────────────────────


def vormerkungen_abfragen(
    session: Session, mitglied_id: uuid.UUID, heute: date
) -> list[dict]:
    """Story 0705: Gibt aktive Vormerkungen + Reservierungen eines Mitglieds zurück."""
    prüfe_reservierungsverfall(session, heute)

    stmt = (
        select(Vormerkung)
        .where(
            Vormerkung.mitglied_id == mitglied_id,
            Vormerkung.status == VormerkungStatus.aktiv,
        )
        .order_by(Vormerkung.eingangszeit)
    )
    vormerkungen = list(session.exec(stmt).all())

    ergebnis = []
    for vm in vormerkungen:
        # Aktive Reservierung suchen
        res = session.exec(
            select(Reservierung).where(
                Reservierung.vormerkung_id == vm.id,
                Reservierung.status == ReservierungStatus.aktiv,
            )
        ).first()
        res_info = None
        if res:
            gegenstand = session.get(Gegenstand, res.gegenstand_id)
            res_info = {
                "gegenstandId": gegenstand.inventarnummer if gegenstand else str(res.gegenstand_id),
                "reserviertBis": res.verfall_datum.isoformat(),
            }

        # Position in Queue
        alle = session.exec(
            select(Vormerkung).where(
                Vormerkung.kategorie_id == vm.kategorie_id,
                Vormerkung.status == VormerkungStatus.aktiv,
            ).order_by(Vormerkung.eingangszeit)
        ).all()
        pos = next((i + 1 for i, v in enumerate(alle) if v.id == vm.id), 1)

        kategorie = session.get(Kategorie, vm.kategorie_id)
        ergebnis.append({
            "vormerkungId": vm.id,
            "kategorieId": vm.kategorie_id,
            "kategorieName": kategorie.name if kategorie else "",
            "eingangszeit": vm.eingangszeit,
            "status": vm.status.value,
            "positionInSchlange": pos,
            "reservierung": res_info,
        })
    return ergebnis
