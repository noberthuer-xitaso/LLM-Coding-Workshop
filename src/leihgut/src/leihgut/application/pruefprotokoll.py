"""Application Use Cases für EPIC-0400: Rückgabe & Prüfung, EPIC-0500: Kaution.

Issue: # 0401, # 0402, # 0403, # 0502, # 0503, # 0504
IOSP: reine Integration — orchestriert DB-Zugriff, keine eigene Berechnungslogik.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from leihgut.application.audit import erfasse_kautionsbewegung, erfasse_zustandswechsel
from leihgut.domain.models import (
    Ausleihe,
    AusleiheStatus,
    Gegenstand,
    GegenstandZustand,
    Kautionsbewegung,
    KautionsbewegungArt,
    Mitglied,
    Pruefprotokoll,
    PruefprotokollNachzustand,
    Reservierung,
    ReservierungStatus,
    Vormerkung,
    VormerkungStatus,
)
from leihgut.domain.regeln import (
    bestimme_effektiven_nachzustand,
    ist_mitglied_gesperrt,
    prüfe_kautionsabzug,
)
from leihgut.infrastructure.datum import SystemDatumsQuelle

# ─────────────────────────────────────────────
#  Globale DatumsQuelle (überschreibbar in Tests)
# ─────────────────────────────────────────────

_datumsquelle = SystemDatumsQuelle()


def set_datumsquelle(dq) -> None:
    global _datumsquelle
    _datumsquelle = dq


# ─────────────────────────────────────────────
#  Anwendungsausnahmen
# ─────────────────────────────────────────────


class AusleiheNichtGefunden(Exception):
    def __init__(self, ausleihe_id: str) -> None:
        self.ausleihe_id = ausleihe_id


class MitgliedNichtGefunden(Exception):
    def __init__(self, mitglied_id: str) -> None:
        self.mitglied_id = mitglied_id


class GegenstandNichtAusgeliehen(Exception):
    pass


class AusleiheNichtInPruefung(Exception):
    pass


class PruefprotokollBereitsVorhanden(Exception):
    pass


class KautionsabzugZuHoch(Exception):
    pass


class AusleiheNichtAktiv(Exception):
    pass


# ─────────────────────────────────────────────
#  Interne Hilfsfunktionen
# ─────────────────────────────────────────────


def _ist_gesperrt(session: Session, mitglied_id: uuid.UUID, heute: date) -> bool:
    aktive = list(session.exec(
        select(Ausleihe).where(
            Ausleihe.mitglied_id == mitglied_id,
            Ausleihe.status == AusleiheStatus.aktiv,
        )
    ).all())
    return ist_mitglied_gesperrt(aktive, heute)


def _letztes_pruefprotokoll_fuer_gegenstand(
    session: Session,
    gegenstand_id: uuid.UUID,
    aktuelle_ausleihe_id: uuid.UUID,
) -> Optional[Pruefprotokoll]:
    """Q7/BR-16: Letztes Protokoll desselben Gegenstands (nicht die aktuelle Ausleihe)."""
    stmt = (
        select(Pruefprotokoll)
        .join(Ausleihe, Pruefprotokoll.ausleihe_id == Ausleihe.id)
        .where(
            Ausleihe.gegenstand_id == gegenstand_id,
            Pruefprotokoll.ausleihe_id != aktuelle_ausleihe_id,
        )
        .order_by(Pruefprotokoll.erstellt_am.desc())
    )
    return session.exec(stmt).first()


# ─────────────────────────────────────────────
#  BR-30/33: Reservierungslogik
# ─────────────────────────────────────────────


def versuche_reservierung_anlegen(
    session: Session,
    gegenstand: Gegenstand,
    heute: date,
) -> Optional[uuid.UUID]:
    """BR-30/33: Nimmt nächste nicht-gesperrte Vormerkung aus Queue.

    Gibt mitglied_id zurück wenn reserviert, sonst None.
    Gesperrte Mitglieder werden übersprungen, behalten Platz (BR-33).
    """
    stmt = (
        select(Vormerkung)
        .where(
            Vormerkung.kategorie_id == gegenstand.kategorie_id,
            Vormerkung.status == VormerkungStatus.aktiv,
        )
        .order_by(Vormerkung.eingangszeit)
    )
    vormerkungen = list(session.exec(stmt).all())

    for vm in vormerkungen:
        if _ist_gesperrt(session, vm.mitglied_id, heute):
            continue  # BR-33: Platz bleibt

        reservierung = Reservierung(
            gegenstand_id=gegenstand.id,
            mitglied_id=vm.mitglied_id,
            vormerkung_id=vm.id,
            erstellt_am=heute,
            verfall_datum=heute + timedelta(days=3),
        )
        session.add(reservierung)
        vm.status = VormerkungStatus.storniert
        session.add(vm)
        gegenstand.zustand = GegenstandZustand.reserviert
        session.add(gegenstand)
        return vm.mitglied_id

    return None


# ─────────────────────────────────────────────
#  UC-0401: Gegenstand zurücknehmen
# ─────────────────────────────────────────────


def rueckgabe_erfassen(
    session: Session,
    ausleihe_id: uuid.UUID,
    heute: date,
    auffaelligkeiten: Optional[str] = None,
) -> Ausleihe:
    """UC-0401: Gegenstand zurücknehmen — setzt Ausleihe und Gegenstand in_Prüfung."""
    ausleihe = session.get(Ausleihe, ausleihe_id)
    if not ausleihe:
        raise AusleiheNichtGefunden(str(ausleihe_id))

    gegenstand = session.get(Gegenstand, ausleihe.gegenstand_id)

    if ausleihe.status != AusleiheStatus.aktiv:
        raise GegenstandNichtAusgeliehen()
    if gegenstand and gegenstand.zustand != GegenstandZustand.ausgeliehen:
        raise GegenstandNichtAusgeliehen()

    altzustand = gegenstand.zustand.value if gegenstand else GegenstandZustand.ausgeliehen.value
    jetzt = datetime.now()

    ausleihe.rueckgabe_datum = heute
    if auffaelligkeiten is not None:
        ausleihe.auffaelligkeiten = auffaelligkeiten
    ausleihe.status = AusleiheStatus.in_pruefung
    session.add(ausleihe)

    if gegenstand:
        gegenstand.zustand = GegenstandZustand.in_pruefung
        session.add(gegenstand)

    session.commit()
    session.refresh(ausleihe)

    if gegenstand:
        erfasse_zustandswechsel(
            session,
            gegenstand.id,
            altzustand,
            GegenstandZustand.in_pruefung.value,
            jetzt,
            ausleihe_id=ausleihe.id,
        )

    return ausleihe


# ─────────────────────────────────────────────
#  UC-0402: Prüfprotokoll erstellen
# ─────────────────────────────────────────────


def pruefprotokoll_erstellen(
    session: Session,
    ausleihe_id: uuid.UUID,
    wart_id: str,
    nachzustand: PruefprotokollNachzustand,
    kautionsabzug: int,
    begruendung: Optional[str],
    heute: date,
) -> Pruefprotokoll:
    """UC-0402: Prüfprotokoll erstellen — BR-14..19, BR-23, BR-24, BR-30."""
    # 1. Ausleihe in_Prüfung?
    ausleihe = session.get(Ausleihe, ausleihe_id)
    if not ausleihe:
        raise AusleiheNichtGefunden(str(ausleihe_id))
    if ausleihe.status != AusleiheStatus.in_pruefung:
        raise AusleiheNichtInPruefung()

    # 2. Pruefprotokoll bereits vorhanden?
    vorhandenes = session.exec(
        select(Pruefprotokoll).where(Pruefprotokoll.ausleihe_id == ausleihe_id)
    ).first()
    if vorhandenes:
        raise PruefprotokollBereitsVorhanden()

    # 3. BR-21: Kautionsabzug prüfen (außer bei verloren — wird überschrieben)
    if nachzustand != PruefprotokollNachzustand.verloren:
        if prüfe_kautionsabzug(kautionsabzug, ausleihe.kaution_betrag):
            raise KautionsabzugZuHoch()

    gegenstand = session.get(Gegenstand, ausleihe.gegenstand_id)
    if gegenstand is None:
        raise ValueError(f"Gegenstand nicht gefunden für Ausleihe {ausleihe_id}")

    from leihgut.domain.models import Kategorie
    kategorie = session.get(Kategorie, gegenstand.kategorie_id)
    wartungsintervall = kategorie.wartungsintervall_ausleihen if kategorie else 999_999

    # 4. Nutzungszähler erhöhen (BR-23)
    gegenstand.nutzungszaehler += 1
    nutzungszaehler_neu = gegenstand.nutzungszaehler

    # 5. Effektiven Nachzustand bestimmen (BR-19/24)
    nachzustand_eingabe = nachzustand
    effektiver_zustand_str = bestimme_effektiven_nachzustand(
        nachzustand.value, nutzungszaehler_neu, wartungsintervall
    )

    # BR-19: verloren → volle Kaution einbehalten
    if nachzustand == PruefprotokollNachzustand.verloren:
        kautionsabzug = ausleihe.kaution_betrag

    kaution_freigegeben = 0
    altzustand = gegenstand.zustand.value
    jetzt = datetime.now()

    # 7. Ausleihe abschließen
    ausleihe.status = AusleiheStatus.abgeschlossen
    session.add(ausleihe)

    # 8. Gegenstandszustand setzen
    reserviert_fuer: Optional[uuid.UUID] = None

    if effektiver_zustand_str == "wartungsfällig":
        gegenstand.zustand = GegenstandZustand.wartungsfaellig
    elif effektiver_zustand_str == "ausgemustert":
        gegenstand.zustand = GegenstandZustand.ausgemustert
    else:  # "verfügbar" — BR-30: Vormerkungsqueue prüfen
        gegenstand.zustand = GegenstandZustand.verfuegbar
        reserviert_fuer = versuche_reservierung_anlegen(session, gegenstand, heute)

    session.add(gegenstand)

    # 10. Prüfprotokoll anlegen
    protokoll = Pruefprotokoll(
        ausleihe_id=ausleihe.id,
        wart_id=wart_id,
        erstellt_am=jetzt,
        kautionsabzug=kautionsabzug,
        nachzustand=nachzustand_eingabe,
        begruendung=begruendung,
    )
    session.add(protokoll)
    session.commit()
    session.refresh(protokoll)
    session.refresh(gegenstand)

    # 6. Kautionsbewegungen erfassen (BR-22) — nach commit, damit protokoll.id bekannt
    if nachzustand == PruefprotokollNachzustand.verloren:
        erfasse_kautionsbewegung(
            session, ausleihe.id, KautionsbewegungArt.einbehaltung,
            ausleihe.kaution_betrag, jetzt, referenz_id=protokoll.id,
        )
    else:
        if kautionsabzug > 0:
            erfasse_kautionsbewegung(
                session, ausleihe.id, KautionsbewegungArt.abzug,
                kautionsabzug, jetzt, referenz_id=protokoll.id,
            )
        kaution_freigegeben = ausleihe.kaution_betrag - kautionsabzug
        if kaution_freigegeben > 0:
            erfasse_kautionsbewegung(
                session, ausleihe.id, KautionsbewegungArt.freigabe,
                kaution_freigegeben, jetzt, referenz_id=protokoll.id,
            )

    # 9. Zustandswechsel-Audit
    erfasse_zustandswechsel(
        session,
        gegenstand.id,
        altzustand,
        gegenstand.zustand.value,
        jetzt,
        ausleihe_id=ausleihe.id,
        pruefprotokoll_id=protokoll.id,
    )

    # Vorheriges Prüfprotokoll für selben Gegenstand (Q7, BR-16)
    vorheriges = _letztes_pruefprotokoll_fuer_gegenstand(session, gegenstand.id, ausleihe.id)

    # Transiente Attribute für API-Antwort
    object.__setattr__(protokoll, "nachzustand_eingabe", nachzustand_eingabe)
    object.__setattr__(protokoll, "nachzustand_effektiv", gegenstand.zustand.value)
    object.__setattr__(protokoll, "kaution_freigegeben", kaution_freigegeben)
    object.__setattr__(protokoll, "reserviert_fuer", reserviert_fuer)
    object.__setattr__(protokoll, "gegenstand_inventarnummer", gegenstand.inventarnummer)
    object.__setattr__(protokoll, "vorheriges_pruefprotokoll_id", vorheriges.id if vorheriges else None)

    return protokoll


# ─────────────────────────────────────────────
#  UC-0403: Gegenstand als verloren erklären
# ─────────────────────────────────────────────


def verloren_erklaeren(
    session: Session,
    ausleihe_id: uuid.UUID,
    wart_id: str,
    heute: date,
) -> Pruefprotokoll:
    """UC-0403: Laufende Ausleihe als verloren erklären — OHNE Rückgabe (BR-19)."""
    ausleihe = session.get(Ausleihe, ausleihe_id)
    if not ausleihe:
        raise AusleiheNichtGefunden(str(ausleihe_id))

    if ausleihe.status != AusleiheStatus.aktiv:
        raise AusleiheNichtAktiv()

    vorhandenes = session.exec(
        select(Pruefprotokoll).where(Pruefprotokoll.ausleihe_id == ausleihe_id)
    ).first()
    if vorhandenes:
        raise PruefprotokollBereitsVorhanden()

    # Ausleihe in_Prüfung schalten, damit pruefprotokoll_erstellen akzeptiert
    ausleihe.status = AusleiheStatus.in_pruefung
    session.add(ausleihe)
    session.commit()

    return pruefprotokoll_erstellen(
        session=session,
        ausleihe_id=ausleihe_id,
        wart_id=wart_id,
        nachzustand=PruefprotokollNachzustand.verloren,
        kautionsabzug=0,  # wird intern überschrieben
        begruendung=None,
        heute=heute,
    )


# ─────────────────────────────────────────────
#  UC-0504: Kautionsbewegungen abfragen
# ─────────────────────────────────────────────


def kautionsbewegungen_abfragen(
    session: Session,
    mitglied_id: uuid.UUID,
    ausleihe_id_filter: Optional[uuid.UUID] = None,
) -> list[Kautionsbewegung]:
    """UC-0504: Kautionsbewegungen aller Ausleihen eines Mitglieds."""
    mitglied = session.get(Mitglied, mitglied_id)
    if not mitglied:
        raise MitgliedNichtGefunden(str(mitglied_id))

    stmt = (
        select(Kautionsbewegung)
        .join(Ausleihe, Kautionsbewegung.ausleihe_id == Ausleihe.id)
        .where(Ausleihe.mitglied_id == mitglied_id)
    )
    if ausleihe_id_filter is not None:
        stmt = stmt.where(Kautionsbewegung.ausleihe_id == ausleihe_id_filter)

    return list(session.exec(stmt).all())
