# Domain-Driven Design Analysis: Leihgut System
## Complete Index & Quick Navigation

---

## 📋 Document Overview

**Full Analysis File**: `/workspaces/LLM-Coding-Workshop/DDD_ANALYSIS.md` (578 lines)

This index provides quick navigation to key sections of the comprehensive DDD analysis.

---

## 🎯 Executive Summary

### Single Bounded Context: Leihgut
- **Name**: Leihgut (Tool Lending / Equipment Rental System)
- **Type**: Single, unified bounded context with 8 internal subdomains
- **No External Dependencies**: No cross-context communication
- **Architecture**: Hexagonal (Ports & Adapters) with strict domain separation

### 8 Internal Subdomains:
1. **Lending Lifecycle** - Equipment checkout, return, extension
2. **Equipment Catalog** - Inventory, categories, metadata
3. **Security Deposits** - Collateral calculation, tracking, refunds
4. **Maintenance & Inspection** - Damage tracking, maintenance cycles
5. **Training Requirements** - Member certifications for restricted equipment
6. **Reservation & Queuing** - FIFO reservation management
7. **Extension & Loss** - Loan extension, loss declaration
8. **Audit & Compliance** - Immutable audit trail, retention policies

---

## 🏛️ Architecture Layers

### Domain Layer (Pure Business Logic)
**Location**: `/workspaces/LLM-Coding-Workshop/src/leihgut/domain/`

**Core Entities** (with state machines):
- `Ausleihe` (4 states): AKTIV → ZURUECKGEGEBEN → ABGESCHLOSSEN | ABGESCHLOSSEN_VERLOREN
- `Gegenstand` (6 states): VERFUEGBAR, AUSGELIEHEN, IN_PRUEFUNG, WARTUNGSFAELLIG, RESERVIERT, AUSGEMUSTERT
- `Einweisung` (2 states): VALID (until widerrufen_am IS NULL) | REVOKED
- `Vormerkung` (3 states): OFFEN, AUTOMATISCH_ABGESAGT, MANUELL_ABGESAGT

**Value Objects**:
- `Kategorie`: Equipment type (leihdauer_tage, wartungsintervall, einweisungspflichtig)
- `Kaution`: Pure calculation function (20% of replacement value, bounded €5-€100)
- `Kautionsbewegung`: Transaction log (HINTERLEGUNG, ABZUG, FREIGABE, VERLUST_EINZUG)
- `MaengelEintrag`: Damage record with deduplication
- `AuditLogEintrag`: Immutable audit entry

**File:Line References**:
- `ausleihe.py:14-40` - Ausleihe aggregate
- `gegenstand.py:10-30` - Gegenstand aggregate
- `kategorie.py:9-15` - Kategorie value object
- `einweisung.py:10-20` - Einweisung aggregate
- `vormerkung.py:12-29` - Vormerkung aggregate
- `kaution.py:7-20` - Kaution pure function
- `pruefprotokoll.py:11-18` - Pruefprotokoll aggregate
- `maengel.py:11-16` - MaengelEintrag value object
- `audit_log.py:12-20` - AuditLogEintrag value object
- `kautionsbewegung.py:14-28` - Kautionsbewegung value object

### Application Services Layer (Use Case Orchestration)
**Location**: `/workspaces/LLM-Coding-Workshop/src/leihgut/anwendungskern/`

**Services**:
- `ausleihe_service.py` - UC-01 (checkout), UC-03 (return)
- `verlaengerung_service.py` - UC-02 (extend loan)
- `pruefung_service.py` - UC-04 (inspection/closure)
- `wartung_service.py` - UC-05 (maintenance complete)
- `verlust_service.py` - UC-06 (loss declaration)
- `einweisung_service.py` - UC-07/08 (training)
- `katalog_service.py` - UC-09 (inventory management)
- `vormerkung_service.py` - UC-05 (reservations)
- `verfuegbarkeit_service.py` - UC-10 (availability check)
- `audit_retention_service.py` - Maintenance (audit cleanup)

**Pattern**: IOSP (Input-Operation-Storage-Port)
- Pure operations (no ports) for isolated unit testing
- Integration functions (with ports) for service-level testing

### Port Layer (Hexagonal Abstraction)
**Location**: `/workspaces/LLM-Coding-Workshop/src/leihgut/ports/`

**9 Protocol Ports** (Python interfaces, no concrete dependencies):
1. `AusleiheRepository` - Loan persistence
2. `GegenstandRepository` - Equipment persistence
3. `KategorieRepository` - Category persistence
4. `EinweisungRepository` - Training persistence
5. `VormerkungRepository` - Reservation persistence
6. `MaengelRepository` - Damage persistence
7. `PruefabschlussRepository` - Atomic inspection transactions
8. `AuditLogRepository` - Audit log persistence (append-only)
9. `Clock` - Time provider (for testable time-dependent logic)

### Adapter Layer (External Integration)
**Location**: `/workspaces/LLM-Coding-Workshop/src/leihgut/adapters/`

**Persistence Adapters**:
- `sqlite_ausleihe_repository.py`
- `sqlite_gegenstand_repository.py`
- `sqlite_kategorie_repository.py`
- `sqlite_einweisung_repository.py`
- `sqlite_vormerkung_repository.py`
- `sqlite_maengel_repository.py`
- `sqlite_pruefabschluss_repository.py`
- `sqlite_audit_log_repository.py`

**System Adapters**:
- `system_clock.py` - Clock port implementation

**REST Adapter**:
- `rest/app.py` - FastAPI endpoint routing (line 144-593)
- `rest/schemas.py` - Pydantic request/response models
- `rest/rollen.py` - Role-based access control

**Database**:
- `persistence/schema.sql` - Complete SQLite schema with constraints

---

## 🔀 Inter-Service Communication

**Within Bounded Context**:
- **ausleihe_service** → **vormerkung_service** (after UC-03 return)
  - Call: `vormerkungs_verwalten_nach_rueckgabe(vormerkung_repo, kategorie_id)`
  - Purpose: Auto-cancel first reservation after equipment return
  - Location: `ausleihe_service.py:292`

**Via Shared Repositories**:
- All other service interactions through repository ports
- ACID transactions ensure consistency
- No explicit events, no message buses
- No cross-context communication

---

## 📊 Business Rules Traceability

### Total: 25+ Business Rules (All Traceable)

**Availability & Checkout (BR-AUS-*)**:
| Rule | Location | Enforced By |
|------|----------|-------------|
| BR-AUS-01 | Equipment available OR (reserved AND for member) | ausleihe_service.py:122-130 | Domain + DB index |
| BR-AUS-02 | Max 3 loans per member | ausleihe_service.py:135 | App validation |
| BR-AUS-03 | Block overdue members from checkout | ausleihe_service.py:163 | App validation |
| BR-AUS-04 | Training required for restricted items | ausleihe_service.py:137 | App validation |
| BR-AUS-05 | Kaution frozen at checkout (not dynamic) | ausleihe_service.py:194 | Snapshot-based design |
| BR-AUS-06 | One extension maximum | verlaengerung_service.py:138 | App validation |
| BR-AUS-07 | Cannot extend if overdue | verlaengerung_service.py:125 | App validation |

**Catalog (BR-KAT-*)**:
| BR-KAT-01 | Unique inventory numbers | katalog_service.py:144 | DB primary key |
| BR-KAT-02 | Positive leihdauer_tage & wartungsintervall | katalog_service.py:59-68 | App validation |
| BR-KAT-03 | Positive wiederbeschaffungswert_cent | katalog_service.py:71-75 | App validation |
| BR-KAT-04 | Kaution = 20% × replacement [€5, €100] | kaution.py:12-20 | Pure function (centralized) |

**Inspection & Maintenance (BR-RUP-*, BR-WAR-*)**:
| BR-RUP-01 | Equipment → IN_PRUEFUNG after return | ausleihe_service.py:285 | App logic |
| BR-RUP-04 | Loan → ABGESCHLOSSEN after inspection | pruefung_service.py:193 | App logic |
| BR-RUP-05 | Damage deduplication by exact description | pruefung_service.py:132-145 | App logic |
| BR-WAR-01 | Increment usage counter on inspection | pruefung_service.py:148 | App logic |
| BR-WAR-02 | Maintenance if usage ≥ wartungsintervall | pruefung_service.py:93-94 | App logic |
| BR-WAR-03 | Reset counter to 0 after maintenance | wartung_service.py:118 | App logic |

**Security Deposits (BR-KAU-*)**:
| BR-KAU-02 | Deduction ≤ hinterlegte kaution | pruefung_service.py:78 | App validation |
| BR-KAU-03/04 | Loss → 100% deposit seizure | verlust_service.py:129 | App logic |

**Training (BR-EIN-*)**:
| BR-EIN-01 | Max 1 valid training per member/category | einweisung_service.py:75 | DB index + app |
| BR-EIN-02 | Training valid indefinitely until revoked | einweisung.py:18-20 | Domain logic |

**Reservations (BR-VOR-*)**:
| BR-VOR-01 | Max 1 open reservation per member/category | vormerkung_service.py:86 | DB index + app |
| BR-VOR-02 | FIFO queue (reihenfolge 1-based) | vormerkung_service.py:51-53 | App sorting |
| BR-VOR-03 | After maintenance, RESERVIERT if queue exists | wartung_service.py:105-107 | App logic |

**Loss (BR-VER-*)**:
| BR-VER-01/02 | Loss → ABGESCHLOSSEN_VERLOREN | verlust_service.py:102 | Atomic update |
| BR-VER-03 | Lost equipment → AUSGEMUSTERT | verlust_service.py:115 | Atomic update |

**Member Status (BR-SPE-*)**:
| BR-SPE-02 | Block if ANY loan overdue | ausleihe_service.py:163 | App validation |

---

## 🔐 Data Consistency & Integrity

### Database Layer (ADR-007, ADR-009)
**Constraints in Schema**:
```sql
-- Prevent simultaneous active loans (UC-01 protection)
CREATE UNIQUE INDEX ux_ausleihe_aktiv_je_gegenstand
    ON ausleihe (gegenstand_id)
    WHERE zustand = 'aktiv'

-- Audit log immutability
CREATE TRIGGER trg_audit_log_no_update BEFORE UPDATE … RAISE(ABORT)
CREATE TRIGGER trg_audit_log_no_delete BEFORE DELETE … RAISE(ABORT)

-- Prevent duplicate trainings
CREATE UNIQUE INDEX ux_einweisung_gueltig_je_mitglied_kategorie
    ON einweisung (mitglied_id, kategorie_id)
    WHERE widerrufen_am IS NULL

-- Prevent duplicate open reservations
CREATE UNIQUE INDEX ux_vormerkung_offen_je_mitglied_kategorie
    ON vormerkung (mitglied_id, kategorie_id)
    WHERE status = 'offen'
```

### Application Layer
**BEGIN IMMEDIATE Transactions**:
- `ausleihe_service.py:206` - UC-01 checkout (BEGIN before validation)
- `verlust_service.py:86-90` - UC-06 loss (BEGIN before validation)
- Prevents TOCTOU races by acquiring write lock early

**Atomic Transactional Ports**:
- `PruefabschlussRepository.abschliessen()` - UC-04
  - Bundles: Ausleihe, Gegenstand, Pruefprotokoll, MaengelEintrag, Kautionsbewegung
  - Single SQLite transaction

**Snapshot-Based Design**:
- `Ausleihe.kaution_cent` - Frozen at UC-01 checkout
- Protects against category change during active loans

---

## 📁 File Structure Summary

```
src/leihgut/
├── domain/                          # Pure domain (10 files, ~300 lines)
│   ├── ausleihe.py                  # Loan aggregate (4-state)
│   ├── gegenstand.py                # Equipment (6-state)
│   ├── kategorie.py                 # Category
│   ├── einweisung.py                # Training (2-state)
│   ├── vormerkung.py                # Reservation (3-state)
│   ├── kaution.py                   # Deposit calculation
│   ├── kautionsbewegung.py          # Deposit transaction
│   ├── maengel.py                   # Damage record
│   ├── pruefprotokoll.py            # Inspection report
│   └── audit_log.py                 # Audit entry
│
├── ports/                           # Hexagonal interfaces (9 ports)
│   ├── ausleihe_repository.py
│   ├── gegenstand_repository.py
│   ├── kategorie_repository.py
│   ├── einweisung_repository.py
│   ├── vormerkung_repository.py
│   ├── maengel_repository.py
│   ├── pruefabschluss_repository.py
│   ├── audit_log_repository.py
│   └── clock.py
│
├── anwendungskern/                  # Application services (10 files, ~2000 lines)
│   ├── ausleihe_service.py          # UC-01, UC-03 (315 lines)
│   ├── verlaengerung_service.py     # UC-02 (177 lines)
│   ├── pruefung_service.py          # UC-04 (231 lines)
│   ├── wartung_service.py           # UC-05 (138 lines)
│   ├── verlust_service.py           # UC-06 (176 lines)
│   ├── einweisung_service.py        # UC-07/08 (159 lines)
│   ├── katalog_service.py           # UC-09 (186 lines)
│   ├── vormerkung_service.py        # UC-05 (164 lines)
│   ├── verfuegbarkeit_service.py    # UC-10 (30 lines)
│   └── audit_retention_service.py   # Maintenance (198 lines)
│
├── adapters/                        # Hexagonal adapters
│   ├── persistence/
│   │   ├── sqlite_*.py              # 8 repository implementations
│   │   └── schema.sql               # Database schema (150+ lines)
│   ├── rest/
│   │   ├── app.py                   # FastAPI (593 lines)
│   │   ├── schemas.py               # Pydantic models (62 lines)
│   │   └── rollen.py                # Access control
│   └── system_clock.py              # Clock adapter
│
└── __init__.py
```

---

## 🧪 Testing Structure

**Location**: `/workspaces/LLM-Coding-Workshop/tests/`

**Test Files** (EPIC-based, Gherkin-style):
- `test_epic_a_ausleihe.py` - UC-01, UC-03
- `test_epic_a2_verlaengerung.py` - UC-02
- `test_epic_b_pruefung_kaution.py` - UC-04
- `test_epic_c_einweisung.py` - UC-07, UC-08
- `test_epic_d_katalog.py` - UC-09, UC-10
- `test_epic_d_katalog_pflegen.py` - UC-09 maintenance
- `test_epic_e_vormerkung.py` - UC-05
- `test_epic_f_verlust.py` - UC-06
- `test_epic_g_wartung.py` - UC-05
- `test_epic_maintenance_audit_retention.py` - Audit cleanup
- `test_skeleton_01_verfuegbarkeit.py` - UC-10
- `fakes.py` - Test doubles (FakeClock, etc.)

---

## 🔗 Use Case to Service Mapping

| UC | Name | Service Function | File:Line |
|---|---|---|---|
| UC-01 | Checkout | `gegenstand_ausgeben()` | ausleihe_service.py:144-246 |
| UC-02 | Extension | `ausleihe_verlaengern()` | verlaengerung_service.py:102-176 |
| UC-03 | Return | `gegenstand_zuruecknehmen()` | ausleihe_service.py:251-314 |
| UC-04 | Inspection | `pruefung_abschliessen()` | pruefung_service.py:100-230 |
| UC-05 | Maintenance | `wartung_abschliessen()` | wartung_service.py:62-137 |
| UC-05 | Reservation | `vormerkung_erfassen()` | vormerkung_service.py:59-115 |
| UC-06 | Loss | `verlust_erfassen()` | verlust_service.py:48-175 |
| UC-07 | Training | `einweisung_erfassen()` | einweisung_service.py:55-108 |
| UC-08 | Revoke Training | `einweisung_widerrufen()` | einweisung_service.py:114-158 |
| UC-09 | Inventory | `kategorie_anlegen()`, etc. | katalog_service.py |
| UC-10 | Availability | `verfuegbarkeit_pruefen()` | verfuegbarkeit_service.py:21-29 |

---

## 🛠️ Technology Stack

- **Language**: Python 3.11+
- **REST Framework**: FastAPI 0.115+
- **Database**: SQLite (single file, in-process)
- **Validation**: Pydantic 2.7+
- **CLI**: Typer 0.12+
- **Testing**: Pytest 8.0+ with Hypothesis 6.100+

---

## 📚 Key References in Code

**Architecture Decisions** (ADRs):
- ADR-004: SQLite single file
- ADR-005: Single writer (no concurrent processes)
- ADR-006: Clock abstraction for testability
- ADR-007: BEGIN IMMEDIATE + partial index for TOCTOU
- ADR-009: Audit log immutability via trigger

**Domain-Driven Design Patterns**:
- Aggregate (Ausleihe, Gegenstand, Einweisung, Vormerkung)
- Value Object (Kategorie, Kaution, MaengelEintrag, AuditLogEintrag)
- Repository Pattern (9 ports)
- Service Layer (10 application services)
- Domain Event (via audit log)
- Ubiquitous Language (German domain terminology)

**Architectural Patterns**:
- Hexagonal Architecture (ports + adapters)
- IOSP (Input-Operation-Storage-Port)
- ACID Transactions (SQLite)
- State Machine (enums for entity lifecycles)

---

## ✅ Key Takeaways

1. **Single Bounded Context**: All 8 subdomains operate within a unified Leihgut domain
2. **No External Dependencies**: No cross-context communication or anti-corruption layers
3. **Hexagonal Architecture**: Strict separation via 9 protocol ports
4. **Comprehensive Business Rules**: 25+ rules traceable to specific code locations
5. **Dual-Layer Consistency**: Database constraints + application validation
6. **Immutable Audit Trail**: Append-only by design (ADR-009)
7. **Testable Design**: IOSP pattern, fake implementations, ACID isolation
8. **Clear Responsibility**: 8 subdomains, 10 services, 6 major aggregates

---

**Full Analysis**: `/workspaces/LLM-Coding-Workshop/DDD_ANALYSIS.md`

Generated: 2025 | Analyzed: `/workspaces/LLM-Coding-Workshop/src/leihgut/`
