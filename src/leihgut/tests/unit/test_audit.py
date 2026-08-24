"""Unit-Tests für EPIC-0900: Audit-Log — Service-Funktionen.

Testet erfasse_kautionsbewegung und erfasse_zustandswechsel direkt
mit einer In-Memory-Session-Fixture.
"""

# 0901, 0902

import uuid
from datetime import date, datetime

import pytest
from sqlmodel import Session

from leihgut.application.audit import (
    ZeitraumUngueltig,
    abfragen_audit_eintraege,
    abfragen_audit_eintrag,
    erfasse_kautionsbewegung,
    erfasse_zustandswechsel,
)
from leihgut.domain.models import (
    AuditEintrag,
    AuditTyp,
    Ausleihe,
    AusleiheStatus,
    Gegenstand,
    Kategorie,
    Kautionsbewegung,
    KautionsbewegungArt,
    Mitglied,
)

_JETZT = datetime(2026, 8, 24, 10, 30, 0)


# ─────────────────────────────────────────────
#  Hilfsfunktionen: Testdaten anlegen
# ─────────────────────────────────────────────


def _kategorie(session: Session) -> Kategorie:
    k = Kategorie(
        name="Bohrmaschinen",
        leihdauer_tage=7,
        wartungsintervall_ausleihen=10,
        einweisungspflichtig=False,
    )
    session.add(k)
    session.commit()
    session.refresh(k)
    return k


def _gegenstand(session: Session, kategorie: Kategorie) -> Gegenstand:
    g = Gegenstand(
        inventarnummer="BH-042",
        kategorie_id=kategorie.id,
        wiederbeschaffungswert_euro=100,
    )
    session.add(g)
    session.commit()
    session.refresh(g)
    return g


def _mitglied(session: Session) -> Mitglied:
    m = Mitglied(name="Testmitglied")
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def _ausleihe(session: Session, gegenstand: Gegenstand, mitglied: Mitglied) -> Ausleihe:
    a = Ausleihe(
        gegenstand_id=gegenstand.id,
        mitglied_id=mitglied.id,
        ausgabe_datum=date(2026, 8, 24),
        rueckgabefrist=date(2026, 8, 31),
        kaution_betrag=20,
        status=AusleiheStatus.aktiv,
    )
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


# ─────────────────────────────────────────────
#  Story 0901: erfasse_kautionsbewegung
# ─────────────────────────────────────────────


def test_erfasse_kautionsbewegung_hinterlegung(session: Session):
    """0901 — Hinterlegung erzeugt eine Kautionsbewegung in der DB."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)

    bewegung = erfasse_kautionsbewegung(
        session,
        ausleihe_id=a.id,
        art=KautionsbewegungArt.hinterlegung,
        betrag=20,
        zeitstempel=_JETZT,
    )

    assert bewegung.id is not None
    assert bewegung.ausleihe_id == a.id
    assert bewegung.art == KautionsbewegungArt.hinterlegung
    assert bewegung.betrag == 20
    assert bewegung.zeitstempel == _JETZT
    assert bewegung.referenz_id is None

    # Persistenz prüfen
    aus_db = session.get(Kautionsbewegung, bewegung.id)
    assert aus_db is not None
    assert aus_db.art == KautionsbewegungArt.hinterlegung


def test_erfasse_kautionsbewegung_mit_referenz(session: Session):
    """0901 — Abzug mit Prüfprotokoll-Referenz wird korrekt gespeichert."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)
    protokoll_id = uuid.uuid4()

    bewegung = erfasse_kautionsbewegung(
        session,
        ausleihe_id=a.id,
        art=KautionsbewegungArt.abzug,
        betrag=10,
        zeitstempel=_JETZT,
        referenz_id=protokoll_id,
    )

    assert bewegung.art == KautionsbewegungArt.abzug
    assert bewegung.referenz_id == protokoll_id


def test_erfasse_kautionsbewegung_append_only(session: Session):
    """0901 — Mehrere Bewegungen können für dieselbe Ausleihe existieren."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)

    b1 = erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.hinterlegung, 20, _JETZT)
    b2 = erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.freigabe, 20, _JETZT)

    assert b1.id != b2.id


# ─────────────────────────────────────────────
#  Story 0902: erfasse_zustandswechsel
# ─────────────────────────────────────────────


def test_erfasse_zustandswechsel_minimal(session: Session):
    """0902 — Zustandswechsel ohne Ausleihe-Bezug wird gespeichert."""
    k = _kategorie(session)
    g = _gegenstand(session, k)

    eintrag = erfasse_zustandswechsel(
        session,
        gegenstand_id=g.id,
        altzustand="verfügbar",
        neuzustand="ausgeliehen",
        zeitstempel=_JETZT,
    )

    assert eintrag.id is not None
    assert eintrag.typ == AuditTyp.zustandswechsel
    assert eintrag.altzustand == "verfügbar"
    assert eintrag.neuzustand == "ausgeliehen"
    assert eintrag.gegenstand_id == g.id
    assert eintrag.ausleihe_id is None
    assert eintrag.pruefprotokoll_id is None

    aus_db = session.get(AuditEintrag, eintrag.id)
    assert aus_db is not None


def test_erfasse_zustandswechsel_mit_ausleihe(session: Session):
    """0902 — Zustandswechsel mit Ausleihe- und Protokoll-Referenz."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)
    protokoll_id = uuid.uuid4()

    eintrag = erfasse_zustandswechsel(
        session,
        gegenstand_id=g.id,
        altzustand="ausgeliehen",
        neuzustand="verfügbar",
        zeitstempel=_JETZT,
        ausleihe_id=a.id,
        pruefprotokoll_id=protokoll_id,
    )

    assert eintrag.ausleihe_id == a.id
    assert eintrag.pruefprotokoll_id == protokoll_id


# ─────────────────────────────────────────────
#  Story 0903: Abfrage-Logik (Unit-Level)
# ─────────────────────────────────────────────


def test_abfragen_audit_eintraege_leer(session: Session):
    """0903 — Leere DB liefert leere Liste."""
    eintraege, total = abfragen_audit_eintraege(session)
    assert eintraege == []
    assert total == 0


def test_abfragen_audit_eintraege_basic(session: Session):
    """0903 — Eintrag wird korrekt zurückgegeben."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)
    erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.hinterlegung, 20, _JETZT)

    eintraege, total = abfragen_audit_eintraege(session)

    assert total == 1
    assert len(eintraege) == 1
    e = eintraege[0]
    assert e["art"] == "hinterlegung"
    assert e["betrag_euro"] == 20
    assert e["gegenstand_inventarnummer"] == "BH-042"
    assert e["mitglied_id"] == str(m.id)
    assert e["pruefprotokoll_id"] is None
    assert e["beschreibung"] == "Kaution hinterlegt bei Ausgabe"


def test_abfragen_audit_eintraege_filter_art(session: Session):
    """0903 — Filterung nach art funktioniert."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)
    erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.hinterlegung, 20, _JETZT)
    erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.freigabe, 20, _JETZT)

    eintraege, total = abfragen_audit_eintraege(session, art=KautionsbewegungArt.freigabe)

    assert total == 1
    assert eintraege[0]["art"] == "freigabe"
    assert eintraege[0]["beschreibung"] == "Kaution freigegeben nach Prüfung"


def test_abfragen_audit_eintraege_filter_ausleihe_id(session: Session):
    """0903 — Filterung nach ausleihe_id."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a1 = _ausleihe(session, g, m)
    # Zweite Ausleihe braucht anderen Gegenstand
    g2 = Gegenstand(inventarnummer="BH-099", kategorie_id=k.id, wiederbeschaffungswert_euro=50)
    session.add(g2)
    session.commit()
    session.refresh(g2)
    a2 = _ausleihe(session, g2, m)

    erfasse_kautionsbewegung(session, a1.id, KautionsbewegungArt.hinterlegung, 20, _JETZT)
    erfasse_kautionsbewegung(session, a2.id, KautionsbewegungArt.hinterlegung, 10, _JETZT)

    eintraege, total = abfragen_audit_eintraege(session, ausleihe_id=a1.id)
    assert total == 1
    assert eintraege[0]["ausleihe_id"] == str(a1.id)


def test_abfragen_audit_eintraege_zeitraum_ungueltig(session: Session):
    """0903 — von > bis löst ZeitraumUngueltig aus."""
    with pytest.raises(ZeitraumUngueltig):
        abfragen_audit_eintraege(
            session,
            von=date(2026, 8, 31),
            bis=date(2026, 8, 1),
        )


def test_abfragen_audit_eintraege_paginierung(session: Session):
    """0903 — offset und limit funktionieren korrekt."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)
    for i in range(5):
        erfasse_kautionsbewegung(session, a.id, KautionsbewegungArt.hinterlegung, i + 1, _JETZT)

    eintraege, total = abfragen_audit_eintraege(session, limit=2, offset=1)
    assert total == 5
    assert len(eintraege) == 2


def test_abfragen_audit_eintrag_nicht_gefunden(session: Session):
    """0903 — Unbekannte ID löst AuditEintragNichtGefunden aus."""
    from leihgut.application.audit import AuditEintragNichtGefunden

    with pytest.raises(AuditEintragNichtGefunden):
        abfragen_audit_eintrag(session, uuid.uuid4())


def test_beschreibung_einbehaltung(session: Session):
    """0901 — Einbehaltung hat korrekte Beschreibung."""
    k = _kategorie(session)
    g = _gegenstand(session, k)
    m = _mitglied(session)
    a = _ausleihe(session, g, m)
    protokoll_id = uuid.uuid4()
    erfasse_kautionsbewegung(
        session, a.id, KautionsbewegungArt.einbehaltung, 20, _JETZT, referenz_id=protokoll_id
    )

    eintraege, _ = abfragen_audit_eintraege(session)
    e = eintraege[0]
    assert e["beschreibung"] == "Kaution einbehalten (Verlust)"
    assert e["pruefprotokoll_id"] == str(protokoll_id)
