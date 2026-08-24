"""Application Use Cases für EPIC-0300: Ausleihe + Verlängerung, EPIC-0800: Mitgliedersperre.

Issue: 0301, 0302, 0303, 0304, 0801, 0802
IOSP: reine Integration — orchestriert DB-Zugriff, keine eigene Berechnungslogik.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlmodel import Session, select

from leihgut.application.audit import erfasse_kautionsbewegung, erfasse_zustandswechsel
from leihgut.application.einweisung import hat_einweisung
from leihgut.application.katalog import GegenstandNichtGefunden
from leihgut.domain.models import (
    Ausleihe,
    AusleiheStatus,
    Gegenstand,
    GegenstandZustand,
    KautionsbewegungArt,
    Mitglied,
    ReservierungStatus,
    Reservierung,
    Vormerkung,
    VormerkungStatus,
)
from leihgut.domain.regeln import (
    berechne_kaution,
    ist_mitglied_gesperrt,
    prüfe_ausgabebedingungen,
    prüfe_verlaengerungsbedingungen,
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


class MitgliedGesperrt(Exception):
    pass


class AusleihlimitErreicht(Exception):
    pass


class GegenstandNichtVerfuegbar(Exception):
    pass


class EinweisungFehlt(Exception):
    pass


class GegenstandWartungsfaellig(Exception):
    pass


class AusleiheNichtGefunden(Exception):
    def __init__(self, ausleihe_id: str) -> None:
        self.ausleihe_id = ausleihe_id


class MitgliedNichtGefunden(Exception):
    def __init__(self, mitglied_id: str) -> None:
        self.mitglied_id = mitglied_id


class AusleiheNichtAktiv(Exception):
    pass


class BereitsVerlaengert(Exception):
    pass


class AusleiheUeberfaellig(Exception):
    pass


class VormerkungOffen(Exception):
    pass


# ─────────────────────────────────────────────
#  Interne Hilfsfunktionen
# ─────────────────────────────────────────────


def _hole_gegenstand_by_inventarnummer(session: Session, inventarnummer: str) -> Gegenstand:
    stmt = select(Gegenstand).where(Gegenstand.inventarnummer == inventarnummer)
    gegenstand = session.exec(stmt).first()
    if not gegenstand:
        raise GegenstandNichtGefunden(inventarnummer)
    return gegenstand


def _hole_mitglied(session: Session, mitglied_id: uuid.UUID) -> Mitglied:
    mitglied = session.get(Mitglied, mitglied_id)
    if not mitglied:
        raise MitgliedNichtGefunden(str(mitglied_id))
    return mitglied


def _aktive_ausleihen_fuer_mitglied(session: Session, mitglied_id: uuid.UUID) -> list[Ausleihe]:
    stmt = select(Ausleihe).where(
        Ausleihe.mitglied_id == mitglied_id,
        Ausleihe.status == AusleiheStatus.aktiv,
    )
    return list(session.exec(stmt).all())


def _alle_ausleihen_fuer_mitglied(session: Session, mitglied_id: uuid.UUID) -> list[Ausleihe]:
    stmt = select(Ausleihe).where(Ausleihe.mitglied_id == mitglied_id)
    return list(session.exec(stmt).all())


def _hat_offene_vormerkung_fuer_kategorie(session: Session, kategorie_id: uuid.UUID) -> bool:
    stmt = select(Vormerkung).where(
        Vormerkung.kategorie_id == kategorie_id,
        Vormerkung.status == VormerkungStatus.aktiv,
    )
    return session.exec(stmt).first() is not None


def _ist_ueberfaellig(ausleihe: Ausleihe, heute: date) -> bool:
    return (
        ausleihe.rueckgabefrist < heute
        and ausleihe.status == AusleiheStatus.aktiv
        and ausleihe.rueckgabe_datum is None
    )


# ─────────────────────────────────────────────
#  UC-0301: Ausgabefähigkeit prüfen
# ─────────────────────────────────────────────


def prüfe_ausgabefaehigkeit(
    session: Session,
    inventarnummer: str,
    mitglied_id: uuid.UUID,
    heute: date,
) -> dict:
    """UC-0301: Gibt {"darfAusgegeben": bool, "ablehnungsgruende": list} zurück.

    Wirft keine Exception — alle Fehler erscheinen als Ablehnungsgründe.
    """
    # 404-Fälle werden weitergereicht
    gegenstand = _hole_gegenstand_by_inventarnummer(session, inventarnummer)
    mitglied = _hole_mitglied(session, mitglied_id)

    # Lade Kategorie explizit (lazy loading in Tests nicht immer aktiv)
    from leihgut.domain.models import Kategorie
    if gegenstand.kategorie is None:
        gegenstand.kategorie = session.get(Kategorie, gegenstand.kategorie_id)

    aktive_ausleihen = _aktive_ausleihen_fuer_mitglied(session, mitglied_id)
    alle_ausleihen = _alle_ausleihen_fuer_mitglied(session, mitglied_id)
    gesperrt = ist_mitglied_gesperrt(alle_ausleihen, heute)

    reservierung = session.exec(
        select(Reservierung).where(
            Reservierung.gegenstand_id == gegenstand.id,
            Reservierung.status == ReservierungStatus.aktiv,
        )
    ).first()
    reserviert_fuer = reservierung is not None and reservierung.mitglied_id == mitglied_id

    einweisung = hat_einweisung(session, mitglied_id, gegenstand.kategorie_id)

    gruende = prüfe_ausgabebedingungen(
        gegenstand=gegenstand,
        mitglied_id=mitglied_id,
        aktive_ausleihen_count=len(aktive_ausleihen),
        ist_gesperrt=gesperrt,
        hat_einweisung=einweisung,
        reserviert_fuer_mitglied=reserviert_fuer,
    )

    return {
        "darfAusgegeben": len(gruende) == 0,
        "ablehnungsgruende": gruende,
    }


# ─────────────────────────────────────────────
#  UC-0302: Ausleihe anlegen
# ─────────────────────────────────────────────


def ausleihe_anlegen(
    session: Session,
    inventarnummer: str,
    mitglied_id: uuid.UUID,
    heute: date,
    ausgabedatum: Optional[date] = None,
) -> Ausleihe:
    """UC-0302: Legt eine neue Ausleihe an und führt alle Seiteneffekte aus."""
    gegenstand = _hole_gegenstand_by_inventarnummer(session, inventarnummer)
    mitglied = _hole_mitglied(session, mitglied_id)

    from leihgut.domain.models import Kategorie
    if gegenstand.kategorie is None:
        gegenstand.kategorie = session.get(Kategorie, gegenstand.kategorie_id)

    aktive_ausleihen = _aktive_ausleihen_fuer_mitglied(session, mitglied_id)
    alle_ausleihen = _alle_ausleihen_fuer_mitglied(session, mitglied_id)
    gesperrt = ist_mitglied_gesperrt(alle_ausleihen, heute)

    # BR-07: Gesperrt
    if gesperrt:
        raise MitgliedGesperrt()

    # BR-06: Ausleihlimit
    if len(aktive_ausleihen) >= 3:
        raise AusleihlimitErreicht()

    # BR-03a: Wartungsfällig
    if gegenstand.zustand == GegenstandZustand.wartungsfaellig:
        raise GegenstandWartungsfaellig()

    # BR-05: Verfügbarkeit
    reservierung = session.exec(
        select(Reservierung).where(
            Reservierung.gegenstand_id == gegenstand.id,
            Reservierung.status == ReservierungStatus.aktiv,
        )
    ).first()
    reserviert_fuer = reservierung is not None and reservierung.mitglied_id == mitglied_id

    if gegenstand.zustand not in (GegenstandZustand.verfuegbar, GegenstandZustand.reserviert):
        raise GegenstandNichtVerfuegbar()
    if gegenstand.zustand == GegenstandZustand.reserviert and not reserviert_fuer:
        raise GegenstandNichtVerfuegbar()

    # BR-08: Einweisung
    if gegenstand.kategorie and gegenstand.kategorie.einweisungspflichtig:
        if not hat_einweisung(session, mitglied_id, gegenstand.kategorie_id):
            raise EinweisungFehlt()

    eff_ausgabedatum = ausgabedatum or heute
    leihdauer = gegenstand.kategorie.leihdauer_tage if gegenstand.kategorie else 14
    rueckgabefrist = eff_ausgabedatum.__class__(
        eff_ausgabedatum.year,
        eff_ausgabedatum.month,
        eff_ausgabedatum.day,
    )
    from datetime import timedelta
    rueckgabefrist = eff_ausgabedatum + timedelta(days=leihdauer)

    kaution = berechne_kaution(gegenstand.wiederbeschaffungswert_euro)
    altzustand = gegenstand.zustand.value

    # Ausleihe anlegen
    ausleihe = Ausleihe(
        gegenstand_id=gegenstand.id,
        mitglied_id=mitglied_id,
        ausgabe_datum=eff_ausgabedatum,
        rueckgabefrist=rueckgabefrist,
        kaution_betrag=kaution,
    )
    session.add(ausleihe)

    # Gegenstand-Zustand wechseln
    gegenstand.zustand = GegenstandZustand.ausgeliehen
    gegenstand.nutzungszaehler += 1
    session.add(gegenstand)

    # Reservierung abschließen falls vorhanden
    if reserviert_fuer and reservierung:
        reservierung.status = ReservierungStatus.abgeholt
        session.add(reservierung)

    session.commit()
    session.refresh(ausleihe)

    # Kautionsbewegung + Audit (nach commit, damit ausleihe.id verfügbar)
    jetzt = datetime.now()
    erfasse_kautionsbewegung(session, ausleihe.id, KautionsbewegungArt.hinterlegung, kaution, jetzt)
    erfasse_zustandswechsel(
        session,
        gegenstand.id,
        altzustand,
        GegenstandZustand.ausgeliehen.value,
        jetzt,
        ausleihe_id=ausleihe.id,
    )

    session.refresh(ausleihe)
    return ausleihe


# ─────────────────────────────────────────────
#  UC-0304: Ausleihe(n) abfragen
# ─────────────────────────────────────────────


def ausleihe_abfragen(session: Session, ausleihe_id: uuid.UUID, heute: date) -> Ausleihe:
    """UC-0304: Einzelne Ausleihe; setzt transientes ueberfaellig-Attribut."""
    ausleihe = session.get(Ausleihe, ausleihe_id)
    if not ausleihe:
        raise AusleiheNichtGefunden(str(ausleihe_id))
    object.__setattr__(ausleihe, "ueberfaellig", _ist_ueberfaellig(ausleihe, heute))
    return ausleihe


def ausleihen_abfragen_fuer_mitglied(
    session: Session,
    mitglied_id: uuid.UUID,
    heute: date,
    status_filter: Optional[str] = None,
) -> list[Ausleihe]:
    """UC-0304: Alle Ausleihen eines Mitglieds, optional nach Status gefiltert."""
    mitglied = session.get(Mitglied, mitglied_id)
    if not mitglied:
        raise MitgliedNichtGefunden(str(mitglied_id))

    stmt = select(Ausleihe).where(Ausleihe.mitglied_id == mitglied_id)
    if status_filter:
        stmt = stmt.where(Ausleihe.status == AusleiheStatus(status_filter))
    ausleihen = list(session.exec(stmt).all())
    for a in ausleihen:
        object.__setattr__(a, "ueberfaellig", _ist_ueberfaellig(a, heute))
    return ausleihen


# ─────────────────────────────────────────────
#  UC-0801: Sperrstatus abfragen
# ─────────────────────────────────────────────


def sperrstatus_abfragen(session: Session, mitglied_id: uuid.UUID, heute: date) -> dict:
    """UC-0801/0802: Sperrstatus aus überfälligen Ausleihen ableiten."""
    mitglied = session.get(Mitglied, mitglied_id)
    if not mitglied:
        raise MitgliedNichtGefunden(str(mitglied_id))

    alle_ausleihen = _alle_ausleihen_fuer_mitglied(session, mitglied_id)
    ueberfaellige = [a for a in alle_ausleihen if _ist_ueberfaellig(a, heute)]
    gesperrt = len(ueberfaellige) > 0

    return {
        "mitgliedId": str(mitglied_id),
        "gesperrt": gesperrt,
        "ueberfaelligeAusleihen": len(ueberfaellige),
    }


# ─────────────────────────────────────────────
#  UC-0303: Ausleihe verlängern
# ─────────────────────────────────────────────


def ausleihe_verlaengern(session: Session, ausleihe_id: uuid.UUID, heute: date) -> Ausleihe:
    """UC-0303: Verlängert eine aktive Ausleihe einmalig um die Kategorie-Leihdauer."""
    ausleihe = session.get(Ausleihe, ausleihe_id)
    if not ausleihe:
        raise AusleiheNichtGefunden(str(ausleihe_id))

    if ausleihe.status != AusleiheStatus.aktiv:
        raise AusleiheNichtAktiv()

    # Kategorie für Leihdauer laden
    gegenstand = session.get(Gegenstand, ausleihe.gegenstand_id)
    from leihgut.domain.models import Kategorie
    kategorie = session.get(Kategorie, gegenstand.kategorie_id) if gegenstand else None
    leihdauer = kategorie.leihdauer_tage if kategorie else 14

    hat_offene_vm = _hat_offene_vormerkung_fuer_kategorie(
        session, gegenstand.kategorie_id
    ) if gegenstand else False

    gruende = prüfe_verlaengerungsbedingungen(ausleihe, heute, hat_offene_vm)

    if any("bereits_verlaengert" in g for g in gruende):
        raise BereitsVerlaengert()
    if any("ueberfaellig" in g for g in gruende):
        raise AusleiheUeberfaellig()
    if any("vormerkung_offen" in g for g in gruende):
        raise VormerkungOffen()

    from datetime import timedelta
    ausleihe.rueckgabefrist = ausleihe.rueckgabefrist + timedelta(days=leihdauer)
    ausleihe.verlaengert = True
    session.add(ausleihe)
    session.commit()
    session.refresh(ausleihe)
    return ausleihe
