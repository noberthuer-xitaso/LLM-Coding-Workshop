"""Unit-Tests für Domänenregeln: Vormerkung + Reservierungsverfall.

Issue: 0701, 0702, 0704
IOSP: Service-Level (Application Layer mit In-Memory-Session).
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from leihgut.application.vormerkung import (
    VormerkungBereitsVorhanden,
    prüfe_reservierungsverfall,
    vormerkung_anlegen,
)
from leihgut.domain.models import (
    Gegenstand,
    GegenstandZustand,
    Kategorie,
    Mitglied,
    Reservierung,
    ReservierungStatus,
    Vormerkung,
    VormerkungStatus,
)

HEUTE = date(2026, 9, 1)


# ─────────────────────────────────────────────
#  Session-Fixture (isoliert)
# ─────────────────────────────────────────────


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


# ─────────────────────────────────────────────
#  Hilfsfunktionen
# ─────────────────────────────────────────────


def _kategorie(session: Session, name: str = "Bohrhammer") -> Kategorie:
    k = Kategorie(
        name=name,
        leihdauer_tage=14,
        wartungsintervall_ausleihen=10,
        einweisungspflichtig=False,
    )
    session.add(k)
    session.commit()
    session.refresh(k)
    return k


def _mitglied(session: Session, name: str = "Max Muster") -> Mitglied:
    m = Mitglied(name=name)
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def _gegenstand(session: Session, kategorie: Kategorie, inventarnummer: str = "INV-001") -> Gegenstand:
    g = Gegenstand(
        inventarnummer=inventarnummer,
        kategorie_id=kategorie.id,
        wiederbeschaffungswert_euro=200,
        zustand=GegenstandZustand.verfuegbar,
    )
    session.add(g)
    session.commit()
    session.refresh(g)
    return g


def _vormerkung(
    session: Session,
    mitglied: Mitglied,
    kategorie: Kategorie,
    eingangszeit: datetime,
    status: VormerkungStatus = VormerkungStatus.aktiv,
) -> Vormerkung:
    vm = Vormerkung(
        mitglied_id=mitglied.id,
        kategorie_id=kategorie.id,
        eingangszeit=eingangszeit,
        status=status,
    )
    session.add(vm)
    session.commit()
    session.refresh(vm)
    return vm


# ─────────────────────────────────────────────
#  BR-28: Einmaligkeit je Kategorie
# ─────────────────────────────────────────────


def test_br28_zweite_vormerkung_gleiche_kategorie_abgelehnt(session):
    """BR-28: Mitglied kann je Kategorie nur eine aktive Vormerkung haben."""
    # 0701
    k = _kategorie(session)
    m = _mitglied(session)

    vormerkung_anlegen(session, m.id, k.id, HEUTE)

    with pytest.raises(VormerkungBereitsVorhanden):
        vormerkung_anlegen(session, m.id, k.id, HEUTE)


def test_br28_verschiedene_kategorien_erlaubt(session):
    """BR-28: Mehrere Vormerkungen für unterschiedliche Kategorien sind erlaubt."""
    # 0701
    k1 = _kategorie(session, name="Bohrhammer")
    k2 = _kategorie(session, name="Säge")
    m = _mitglied(session)

    r1 = vormerkung_anlegen(session, m.id, k1.id, HEUTE)
    r2 = vormerkung_anlegen(session, m.id, k2.id, HEUTE)

    assert r1["kategorieId"] == k1.id
    assert r2["kategorieId"] == k2.id


def test_br28_stornierte_vormerkung_erlaubt_neue(session):
    """BR-28: Nach Stornierung kann dieselbe Kategorie erneut vorgemerkt werden."""
    # 0701
    k = _kategorie(session)
    m = _mitglied(session)
    t_alt = datetime(2026, 8, 1, tzinfo=timezone.utc)
    _vormerkung(session, m, k, t_alt, status=VormerkungStatus.storniert)

    result = vormerkung_anlegen(session, m.id, k.id, HEUTE)
    assert result["vormerkungId"] is not None


# ─────────────────────────────────────────────
#  BR-29: FIFO-Reihenfolge
# ─────────────────────────────────────────────


def test_br29_fifo_reihenfolge_position(session):
    """BR-29: Ältere Eingangszeit → kleinere Positionsnummer."""
    # 0701
    k = _kategorie(session)
    m1 = _mitglied(session, name="Erste")
    m2 = _mitglied(session, name="Zweite")
    m3 = _mitglied(session, name="Dritte")

    # Naive Datetimes — SQLite kennt keine Timezones
    t1 = datetime(2026, 8, 1)
    t2 = datetime(2026, 8, 2)
    _vormerkung(session, m1, k, t1)
    _vormerkung(session, m2, k, t2)

    result = vormerkung_anlegen(session, m3.id, k.id, HEUTE)

    assert result["positionInSchlange"] == 3


def test_br29_erste_vormerkung_position_1(session):
    """BR-29: Erste Vormerkung in leerer Queue hat Position 1."""
    # 0701
    k = _kategorie(session)
    m = _mitglied(session)

    result = vormerkung_anlegen(session, m.id, k.id, HEUTE)
    assert result["positionInSchlange"] == 1


# ─────────────────────────────────────────────
#  BR-31: Reservierungsverfall nach 3 Tagen
# ─────────────────────────────────────────────


def test_br31_verfallene_reservierung_wird_auf_verfallen_gesetzt(session):
    """BR-31: Reservierung mit verfall_datum < heute wird auf 'verfallen' gesetzt."""
    # 0704
    k = _kategorie(session)
    m = _mitglied(session)
    g = _gegenstand(session, k)
    vm = _vormerkung(session, m, k, datetime(2026, 8, 1, tzinfo=timezone.utc))

    gestern = HEUTE - timedelta(days=1)
    res = Reservierung(
        gegenstand_id=g.id,
        mitglied_id=m.id,
        vormerkung_id=vm.id,
        erstellt_am=HEUTE - timedelta(days=4),
        verfall_datum=gestern,
        status=ReservierungStatus.aktiv,
    )
    session.add(res)
    session.commit()

    prüfe_reservierungsverfall(session, HEUTE)

    session.refresh(res)
    assert res.status == ReservierungStatus.verfallen


def test_br31_verfall_gibt_gegenstand_frei(session):
    """BR-31: Nach Verfall ohne Folgevormerkung → Gegenstand wieder verfügbar."""
    # 0704
    k = _kategorie(session)
    m = _mitglied(session)
    g = _gegenstand(session, k)
    g.zustand = GegenstandZustand.reserviert
    session.add(g)

    # Stornierte Vormerkung (eingelöst) — keine weitere aktive Vormerkung in Queue
    vm = _vormerkung(session, m, k, datetime(2026, 8, 1), status=VormerkungStatus.storniert)
    res = Reservierung(
        gegenstand_id=g.id,
        mitglied_id=m.id,
        vormerkung_id=vm.id,
        erstellt_am=HEUTE - timedelta(days=4),
        verfall_datum=HEUTE - timedelta(days=1),
        status=ReservierungStatus.aktiv,
    )
    session.add(res)
    session.commit()

    prüfe_reservierungsverfall(session, HEUTE)

    session.refresh(g)
    assert g.zustand == GegenstandZustand.verfuegbar


def test_br31_verfall_loest_folge_reservierung_aus(session):
    """BR-31: Nach Verfall mit Folgevormerkung → Gegenstand reserviert für Nächsten."""
    # 0703, 0704
    k = _kategorie(session)
    m1 = _mitglied(session, name="Erster")
    m2 = _mitglied(session, name="Zweiter")
    g = _gegenstand(session, k)
    g.zustand = GegenstandZustand.reserviert
    session.add(g)

    # vm1 bereits eingelöst (storniert), vm2 wartet aktiv
    vm1 = _vormerkung(session, m1, k, datetime(2026, 8, 1), status=VormerkungStatus.storniert)
    vm2 = _vormerkung(session, m2, k, datetime(2026, 8, 2))
    session.commit()

    res = Reservierung(
        gegenstand_id=g.id,
        mitglied_id=m1.id,
        vormerkung_id=vm1.id,
        erstellt_am=HEUTE - timedelta(days=4),
        verfall_datum=HEUTE - timedelta(days=1),
        status=ReservierungStatus.aktiv,
    )
    session.add(res)
    session.commit()

    prüfe_reservierungsverfall(session, HEUTE)

    session.refresh(g)
    session.refresh(vm2)
    assert g.zustand == GegenstandZustand.reserviert
    assert vm2.status == VormerkungStatus.storniert  # eingelöst


def test_br31_aktive_reservierung_nicht_verfallen(session):
    """BR-31: Reservierung mit verfall_datum >= heute bleibt aktiv."""
    # 0704
    k = _kategorie(session)
    m = _mitglied(session)
    g = _gegenstand(session, k)
    vm = _vormerkung(session, m, k, datetime(2026, 8, 1, tzinfo=timezone.utc))

    res = Reservierung(
        gegenstand_id=g.id,
        mitglied_id=m.id,
        vormerkung_id=vm.id,
        erstellt_am=HEUTE,
        verfall_datum=HEUTE + timedelta(days=3),
        status=ReservierungStatus.aktiv,
    )
    session.add(res)
    session.commit()

    prüfe_reservierungsverfall(session, HEUTE)

    session.refresh(res)
    assert res.status == ReservierungStatus.aktiv
