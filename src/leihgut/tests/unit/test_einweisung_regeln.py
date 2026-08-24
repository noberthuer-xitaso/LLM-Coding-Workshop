"""Unit-Tests für Einweisung-Regeln.

Issue: 0201, 0202, 0203
"""

import uuid
from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from leihgut.domain.models import Einweisung, Kategorie, Mitglied


@pytest.fixture(name="db_session")
def db_session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_hat_einweisung_true(db_session):  # 0201
    """BR-08: Einweisung vorhanden → True."""
    from leihgut.application.einweisung import hat_einweisung

    mitglied = Mitglied(name="Sabine")
    kategorie = Kategorie(name="Kettensäge", leihdauer_tage=7, wartungsintervall_ausleihen=10, einweisungspflichtig=True)
    db_session.add(mitglied)
    db_session.add(kategorie)
    db_session.commit()

    einweisung = Einweisung(
        mitglied_id=mitglied.id,
        kategorie_id=kategorie.id,
        datum=date(2026, 1, 15),
        dokumentiert_von="wart-rolf",
    )
    db_session.add(einweisung)
    db_session.commit()

    assert hat_einweisung(db_session, mitglied.id, kategorie.id) is True


def test_hat_einweisung_false(db_session):  # 0201
    """BR-08: Keine Einweisung → False."""
    from leihgut.application.einweisung import hat_einweisung

    assert hat_einweisung(db_session, uuid.uuid4(), uuid.uuid4()) is False


def test_hat_einweisung_andere_kategorie(db_session):  # 0201
    """BR-08: Einweisung für andere Kategorie gilt nicht."""
    from leihgut.application.einweisung import hat_einweisung

    mitglied = Mitglied(name="Sabine")
    kat_a = Kategorie(name="Bohrer", leihdauer_tage=7, wartungsintervall_ausleihen=10, einweisungspflichtig=True)
    kat_b = Kategorie(name="Säge", leihdauer_tage=7, wartungsintervall_ausleihen=10, einweisungspflichtig=True)
    db_session.add_all([mitglied, kat_a, kat_b])
    db_session.commit()

    einweisung = Einweisung(mitglied_id=mitglied.id, kategorie_id=kat_a.id, datum=date(2026, 1, 1), dokumentiert_von="wart")
    db_session.add(einweisung)
    db_session.commit()

    assert hat_einweisung(db_session, mitglied.id, kat_b.id) is False
