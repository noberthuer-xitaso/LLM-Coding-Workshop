# Domain-Driven Design Bounded Contexts Analysis
## Leihgut – Werkzeugverleih System

Based on the comprehensive analysis of `/workspaces/LLM-Coding-Workshop/src/leihgut/`, this system exhibits a **single, unified bounded context** with the following internal subdomains organized around the business capabilities of a library lending system. The architecture follows hexagonal principles with clear ports, adapters, and domain layers.

---

## BOUNDED CONTEXT: Tool Lending System (Leihgut)

### 1. Name
**Leihgut** (Tool Lending / Equipment Rental)

### 2. Responsibility (Business Capabilities)
The Leihgut system manages the complete lifecycle of equipment lending for a community library ("Bibliothek der Dinge"), handling:
- Equipment checkout and return
- Maintenance tracking and scheduling
- Security deposits (Kaution) management
- Member training requirements (Einweisung)
- Equipment reservations (Vormerkungen)
- Damage tracking (Mängel)
- Loss and decommissioning
- Audit trail and compliance

---

## 3. Core Subdomains & Key Entities

### 3.1 LENDING LIFECYCLE Subdomain
**Responsibility**: Manage the active lending of equipment from checkout to return and testing.

**Key Entities** (file:line evidence):

#### Ausleihe (Loan/Rental Agreement)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/domain/ausleihe.py:14-40`
- **Class**: `Ausleihe` (frozen dataclass)
- **Fields**:
  - `ausleihe_id` (str): Unique loan identifier
  - `gegenstand_id` (str): Equipment reference
  - `mitglied_id` (str): Member reference
  - `ausgabedatum` (str): Checkout date (YYYY-MM-DD)
  - `rueckgabefrist` (str): Return deadline (YYYY-MM-DD)
  - `kaution_cent` (int): Deposited security amount (snapshot)
  - `verlaengert` (bool): Extension flag (BR-AUS-06)
  - `zustand` (AusleiheZustand): State machine with 4 states
  - `rueckgabe_auffaelligkeiten` (str|None): Return condition notes
  - `mitglied_gesperrt` (bool): Member blocked flag
- **State Machine**: `AusleiheZustand` enum (line 14-18)
  - `AKTIV`: Currently checked out
  - `ZURUECKGEGEBEN`: Returned, awaiting inspection
  - `ABGESCHLOSSEN`: Inspection complete, loan closed
  - `ABGESCHLOSSEN_VERLOREN`: Loss declared, item decommissioned
- **Business Logic**:
  - `ist_ueberfaellig(heute: str) -> bool` (line 34-40): Checks if loan is overdue (BR-SPE-02)

#### Ausleihe Service
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/anwendungskern/ausleihe_service.py`
- **Functions**:
  - `gegenstand_ausgeben()` (line 144-246): UC-01, checkout with complete validation
  - `gegenstand_zuruecknehmen()` (line 251-314): UC-03, return and state transition
  - `_ausgabe_pruefen()` (line 107-139): Core business validation (BR-AUS-01 through BR-AUS-04)

---

### 3.2 EQUIPMENT CATALOG Subdomain
**Responsibility**: Maintain equipment inventory, categories, and metadata.

**Key Entities**:

#### Gegenstand (Equipment Item)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/domain/gegenstand.py:10-30`
- **Class**: `Gegenstand` (frozen dataclass)
- **Fields**:
  - `inventarnummer` (str): Unique equipment ID (PK)
  - `kategorie_id` (str): Category reference (FK)
  - `zustand` (GegenstandZustand): Equipment state
  - `wiederbeschaffungswert_cent` (int): Replacement value in cents (BR-KAT-03)
  - `nutzungszaehler` (int): Usage counter for maintenance scheduling (BR-WAR-01)
- **State Machine**: `GegenstandZustand` enum (line 10-19)
  - `VERFUEGBAR`: Available for checkout
  - `AUSGELIEHEN`: Currently checked out
  - `IN_PRUEFUNG`: Returned, undergoing inspection (UC-04)
  - `WARTUNGSFAELLIG`: Maintenance required (BR-WAR-02)
  - `RESERVIERT`: Reserved by first waiting member (BR-VOR-03)
  - `AUSGEMUSTERT`: Decommissioned permanently

#### Kategorie (Equipment Category)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/domain/kategorie.py:9-15`
- **Class**: `Kategorie` (frozen dataclass)
- **Fields**:
  - `kategorie_id` (str): Category identifier
  - `name` (str): Human-readable name
  - `leihdauer_tage` (int): Loan period (BR-KAT-02)
  - `wartungsintervall` (int): Usage count before maintenance required (BR-WAR-01)
  - `einweisungspflichtig` (bool): Training required flag (BR-EIN-01)

#### Katalog Service
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/anwendungskern/katalog_service.py`
- **Functions**:
  - `kategorie_anlegen()` (line 80-99): Create new category (UC-09)
  - `kategorie_aendern()` (line 102-132): Update category parameters (UC-09)
  - `gegenstand_anlegen()` (line 137-159): Add equipment to inventory (UC-09)
  - `gegenstand_wert_aendern()` (line 162-185): Update replacement value

---

### 3.3 SECURITY DEPOSIT (KAUTION) Subdomain
**Responsibility**: Track and manage collateral deposits, deductions, and refunds.

**Key Value Objects**:

#### Kaution (Security Deposit Calculation)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/domain/kaution.py:7-20`
- **Function**: `kaution_berechnen(wiederbeschaffungswert_cent: int) -> int` (line 12-20)
- **Logic**:
  - Calculates: 20% of replacement value (BR-KAT-04)
  - Rounds commercially (kaufmännisch)
  - Bounds: min 5€ (500¢), max 100€ (10,000¢)
  - **Centralized**: Only calculation location in entire system (04_solution_strategy.adoc)

#### Kautionsbewegung (Security Deposit Transaction)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/domain/kautionsbewegung.py:14-28`
- **Class**: `Kautionsbewegung` (frozen dataclass)
- **Fields**:
  - `bewegung_id` (str): Transaction ID
  - `ausleihe_id` (str): Linked loan
  - `art` (KautionsbewegungArt): Transaction type
  - `betrag_cent` (int): Amount
  - `zeitstempel` (str): Timestamp
  - `ausloeser` (str): Role that triggered it
- **Transaction Types** (line 14-18):
  - `HINTERLEGUNG`: Initial deposit (UC-01, not currently used)
  - `ABZUG`: Deduction for damage (UC-04, BR-KAU-02)
  - `FREIGABE`: Refund to member (UC-04)
  - `VERLUST_EINZUG`: Full seizure on loss (UC-06, BR-VER-01/02)

---

### 3.4 MAINTENANCE & INSPECTION Subdomain
**Responsibility**: Record equipment damage, manage maintenance cycles, and closure of loans.

**Key Entities**:

#### Pruefprotokoll (Inspection Report)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/domain/pruefprotokoll.py:11-18`
- **Class**: `Pruefprotokoll` (frozen dataclass)
- **Fields**:
  - `pruefprotokoll_id` (str): Report ID
  - `ausleihe_id` (str): Associated loan
  - `kautionsabzug_cent` (int): Damage-based deduction (BR-RUP-04)
  - `zielzustand` (str): Target equipment state after inspection
  - `erstellt_am` (str): Timestamp
  - `neue_maengel_ids` (list[str]): IDs of newly recorded damage items

#### MaengelEintrag (Damage Record)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/domain/maengel.py:11-16`
- **Class**: `MaengelEintrag` (frozen dataclass)
- **Fields**:
  - `maengel_id` (str): Record ID
  - `gegenstand_id` (str): Equipment reference
  - `beschreibung` (str): Damage description
  - `festgestellt_in_pruefprotokoll_id` (str): Report reference
- **Uniqueness Logic** (BR-RUP-05): Damage deduplication by exact description match

#### Pruefung Service
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/anwendungskern/pruefung_service.py`
- **Functions**:
  - `pruefung_abschliessen()` (line 100-230): UC-04, close loan with inspection
  - `_pruefung_pruefen()` (line 68-80): Validation (BR-KAU-02)
  - `_folgezustand_bestimmen()` (line 83-95): State determination logic (BR-WAR-02)

#### Wartung Service
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/anwendungskern/wartung_service.py`
- **Functions**:
  - `wartung_abschliessen()` (line 62-137): UC-05, close maintenance and return to available
  - Logic: Reset usage counter (BR-WAR-03), check for reservations (BR-VOR-03)

---

### 3.5 TRAINING REQUIREMENTS Subdomain
**Responsibility**: Track member training certifications for restricted equipment.

**Key Entities**:

#### Einweisung (Training Certification)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/domain/einweisung.py:10-20`
- **Class**: `Einweisung` (frozen dataclass)
- **Fields**:
  - `einweisung_id` (str): Certification ID
  - `mitglied_id` (str): Member reference
  - `kategorie_id` (str): Category certified for
  - `erstellt_am` (str): Training date
  - `widerrufen_am` (str|None): Revocation date (BR-EIN-02)
- **Business Logic**:
  - `ist_gueltig() -> bool` (line 18-20): Valid if not revoked (BR-EIN-02)
  - Validity is **indefinite** until explicitly revoked

#### Einweisung Service
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/anwendungskern/einweisung_service.py`
- **Functions**:
  - `einweisung_erfassen()` (line 55-108): UC-07, record training
  - `einweisung_widerrufen()` (line 114-158): UC-08, revoke training
  - Validation: BR-EIN-01 (no duplicates), BR-EIN-02 (immutable until revoked)

---

### 3.6 RESERVATION & QUEUING Subdomain
**Responsibility**: Manage FIFO reservations for popular equipment.

**Key Entities**:

#### Vormerkung (Reservation)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/domain/vormerkung.py:12-29`
- **Class**: `Vormerkung` (frozen dataclass)
- **Fields**:
  - `vormerkung_id` (str): Reservation ID
  - `kategorie_id` (str): Category reserved
  - `mitglied_id` (str): Member reference
  - `erstellt_am` (str): Reservation date
  - `status` (VormerkungStatus): Reservation state
  - `reihenfolge` (int): FIFO position (1-based)
- **State Machine**: `VormerkungStatus` enum (line 12-15)
  - `OFFEN`: Waiting in queue
  - `AUTOMATISCH_ABGESAGT`: Auto-cancelled (7-day window missed, BR-VOR-02)
  - `MANUELL_ABGESAGT`: Manually cancelled
- **Business Logic**:
  - `ist_offen() -> bool` (line 27-29): Active only if status == OFFEN

#### Vormerkung Service
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/anwendungskern/vormerkung_service.py`
- **Functions**:
  - `vormerkung_erfassen()` (line 59-115): UC-05, queue reservation (BR-VOR-01/02)
  - `vormerkungs_verwalten_nach_rueckgabe()` (line 121-147): Auto-cancel first in queue after return
  - `vormerkung_abrufen()` (line 153-163): Retrieve reservation details
  - `_reihenfolge_berechnen()` (line 51-53): Calculate queue position

---

### 3.7 EXTENSION & LOSS Subdomain
**Responsibility**: Handle loan extensions and loss declarations.

#### Verlaengerung Service (Extension)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/anwendungskern/verlaengerung_service.py`
- **Functions**:
  - `ausleihe_verlaengern()` (line 102-176): UC-02, extend loan due date
  - Validation: BR-AUS-06 (one extension max), BR-AUS-07 (not overdue), BR-AUS-08 (member active)
  - Updates: Adds `leihdauer_tage` to current deadline (line 152-160)

#### Verlust Service (Loss)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/anwendungskern/verlust_service.py`
- **Functions**:
  - `verlust_erfassen()` (line 48-175): UC-06, declare equipment lost
  - Atomically updates:
    - Ausleihe → `ABGESCHLOSSEN_VERLOREN` (BR-VER-02)
    - Gegenstand → `AUSGEMUSTERT` (BR-VER-03)
    - Kautionsbewegung: 100% seizure (BR-KAU-03/04)
  - Transactional: `BEGIN IMMEDIATE` (line 86-90)

---

### 3.8 AUDIT & COMPLIANCE Subdomain
**Responsibility**: Maintain immutable audit trail and data retention policies.

**Key Entities**:

#### AuditLogEintrag (Audit Log Entry)
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/domain/audit_log.py:12-20`
- **Class**: `AuditLogEintrag` (frozen dataclass)
- **Fields**:
  - `zeitstempel` (str): Event timestamp (ISO-8601)
  - `aggregat` (str): Entity type (e.g., "Gegenstand", "Ausleihe")
  - `aggregat_id` (str): Entity identifier
  - `ereignisart` (str): Event type (e.g., "zustand_geaendert", "erstellt")
  - `rolle` (str): User role triggering event
  - `werte_vorher` (str|None): Previous state (JSON)
  - `werte_nachher` (str|None): New state (JSON)

#### Audit Retention Service
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/anwendungskern/audit_retention_service.py`
- **Functions**:
  - `cleanup_audit_log()` (line 45-138): UC-Maintenance, purge old entries
  - `get_audit_log_stats()` (line 141-197): Compute audit log metrics
  - Policy:
    - Hot (< 90 days): Queryable in audit_log table
    - Warm (90-365 days): Optional archival (deferred in MVP)
    - Cold (> 1 year): Delete (deferred)
  - **Immutability** (ADR-009): Retention cleanup writes records rather than DELETE

---

## 4. Interfaces to Other Contexts (Cross-Bounded Communication)

### 4.1 Port Layer (Hexagonal Architecture)
**File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/ports/`

All communication is via Protocol interfaces (no concrete dependencies):

#### Repository Ports (Persistence)
1. **AusleiheRepository** (line: `ausleihe_repository.py`)
   - Used by: ausleihe_service, verlaengerung_service, pruefung_service, verlust_service
   - Methods: `find_by_id()`, `finde_offene_fuer_mitglied()`, `insert()`, `update()`

2. **GegenstandRepository** (line: `gegenstand_repository.py`)
   - Used by: ausleihe_service, katalog_service, wartung_service, verfuegbarkeit_service
   - Methods: `find_by_inventarnummer()`, `insert()`, `update()`

3. **KategorieRepository** (line: `kategorie_repository.py`)
   - Used by: ausleihe_service, katalog_service, einweisung_service, vormerkung_service, wartung_service
   - Methods: `find_by_id()`, `insert()`, `update()`

4. **EinweisungRepository** (line: `einweisung_repository.py`)
   - Used by: ausleihe_service, einweisung_service
   - Methods: `find_by_id()`, `find_gueltige_je_mitglied_kategorie()`, `insert()`, `widerrufen()`

5. **VormerkungRepository** (line: `vormerkung_repository.py`)
   - Used by: ausleihe_service, vormerkung_service, wartung_service
   - Methods: `find_by_id()`, `find_offene_je_mitglied_kategorie()`, `find_offene_je_kategorie_sortiert_nach_reihenfolge()`, `insert()`, `update()`

6. **MaengelRepository** (line: `maengel_repository.py`)
   - Used by: pruefung_service
   - Methods: `find_by_gegenstand()`

7. **PruefabschlussRepository** (line: `pruefabschluss_repository.py`)
   - Used by: pruefung_service
   - Methods: `abschliessen()` — **Atomic transactional port**

8. **AuditLogRepository** (line: `audit_log_repository.py`)
   - Used by: ausleihe_service, pruefung_service, einweisung_service, wartung_service, verlust_service
   - Methods: `insert()`

#### System Ports
1. **Clock** (line: `clock.py`)
   - Injected into: All services for date/time
   - Methods: `jetzt() -> str`  (ISO-8601 timestamp)
   - Purpose: Enable testable time-dependent logic (ADR-006)

### 4.2 Domain-Level Integration Points

#### Inter-Service Calls
1. **ausleihe_service** → **vormerkung_service**
   - Location: `ausleihe_service.py:292`
   - Function call: `vormerkungs_verwalten_nach_rueckgabe(vormerkung_repo, gegenstand.kategorie_id)`
   - Context: After successful return (UC-03), auto-cancel first reservation

2. **ausleihe_service** checks Einweisung
   - Location: `ausleihe_service.py:164-166`
   - Via: `einweisung_repo.find_gueltige_je_mitglied_kategorie(mitglied_id, gegenstand.kategorie_id)`
   - Purpose: Validate training requirement before checkout (BR-AUS-04)

3. **ausleihe_service** checks Vormerkung
   - Location: `ausleihe_service.py:171-176`
   - Via: `vormerkung_repo.find_offene_je_kategorie_sortiert_nach_reihenfolge()`
   - Purpose: Validate member matches first reservation if equipment is RESERVIERT

4. **pruefung_service** → Maintenance/Inventory
   - Manages state transitions through Gegenstand (via GegenstandRepository)
   - Interacts with Kategorie (via KategorieRepository) to get maintenance intervals
   - Records defects via MaengelRepository

5. **wartung_service** → **vormerkung_service**
   - Location: `wartung_service.py:98-110`
   - Purpose: After maintenance complete, check if reservations exist to set RESERVIERT state

### 4.3 Adapter Layer (REST API)
**File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/adapters/rest/app.py`

REST endpoints translate HTTP requests to service calls:

#### Use Case Mappings:
1. **POST /gegenstaende/{inv}/ausgabe** → UC-01 `gegenstand_ausgeben()`
2. **POST /ausleihen/{id}/verlaengerung** → UC-02 `ausleihe_verlaengern()`
3. **POST /ausleihen/{id}/rueckgabe** → UC-03 `gegenstand_zuruecknehmen()`
4. **POST /ausleihen/{id}/pruefung** → UC-04 `pruefung_abschliessen()`
5. **POST /gegenstaende/{inv}/wartung** → UC-05 `wartung_abschliessen()`
6. **POST /ausleihen/{id}/verlust** → UC-06 `verlust_erfassen()`
7. **POST /einweisungen** → UC-07 `einweisung_erfassen()`
8. **DELETE /einweisungen/{id}** → UC-08 `einweisung_widerrufen()`
9. **PUT /kategorien/{id}** → UC-09 `kategorie_aendern()`
10. **GET /gegenstaende/{inv}** → UC-10 `verfuegbarkeit_pruefen()`
11. **POST /vormerkungen** → UC-05 `vormerkung_erfassen()`

#### Role-Based Access Control
- **File**: `/workspaces/LLM-Coding-Workshop/src/leihgut/adapters/rest/rollen.py`
- Function: `erfordere_rolle(required_roles: list[str])`
- Roles: `thekendienst` (checkout counter), `wart` (workshop manager), `mitglied` (member)

---

## 5. Shared Data Structures & Domain Events

### 5.1 Value Objects (Immutable, No Identity)
- `GegenstandZustand` (enum): Equipment state
- `AusleiheZustand` (enum): Loan state
- `VormerkungStatus` (enum): Reservation state
- `KautionsbewegungArt` (enum): Deposit transaction type

### 5.2 Implicit Domain Events (Audit Trail)
Events are **implicitly** captured via `AuditLogEintrag` records:
- Gegenstand creation/state change
- Ausleihe creation/state change (active → returned → completed)
- Einweisung creation/revocation
- Pruefabschluss (inspection complete)
- Kautionsbewegung (deposit transaction)
- Verlust (loss declared)
- Wartung completion

No explicit event bus—all writes transactionally coupled to audit inserts.

### 5.3 Foreign Key Relationships
```
kategorie_id → kategorie (category metadata)
gegenstand_id → gegenstand (equipment inventory)
ausleihe_id → ausleihe (loan lifecycle)
pruefprotokoll_id → pruefprotokoll (inspection reports)
mitglied_id → (external, no table) (member identity from upstream system)
```

---

## 6. Module & File Structure

```
src/leihgut/
├── domain/                          # Pure domain logic (no dependencies)
│   ├── ausleihe.py                  # Loan aggregate (4 states)
│   ├── gegenstand.py                # Equipment aggregate (6 states)
│   ├── kategorie.py                 # Category value object
│   ├── einweisung.py                # Training certification aggregate
│   ├── vormerkung.py                # Reservation aggregate (3 states)
│   ├── kaution.py                   # Deposit calculation (pure function)
│   ├── kautionsbewegung.py          # Deposit transaction value object
│   ├── maengel.py                   # Damage record value object
│   ├── pruefprotokoll.py            # Inspection report aggregate
│   └── audit_log.py                 # Audit entry value object
│
├── ports/                           # Hexagonal architecture (Interfaces)
│   ├── ausleihe_repository.py       # Loan persistence protocol
│   ├── gegenstand_repository.py     # Equipment persistence protocol
│   ├── kategorie_repository.py      # Category persistence protocol
│   ├── einweisung_repository.py     # Training persistence protocol
│   ├── vormerkung_repository.py     # Reservation persistence protocol
│   ├── maengel_repository.py        # Damage persistence protocol
│   ├── pruefabschluss_repository.py # Atomic inspection protocol
│   ├── audit_log_repository.py      # Audit persistence protocol
│   └── clock.py                     # Time provider protocol
│
├── anwendungskern/                  # Application services (use cases)
│   ├── ausleihe_service.py          # UC-01, UC-03 (checkout, return)
│   ├── verlaengerung_service.py     # UC-02 (extension)
│   ├── pruefung_service.py          # UC-04 (inspection/closure)
│   ├── wartung_service.py           # UC-05 (maintenance)
│   ├── verlust_service.py           # UC-06 (loss declaration)
│   ├── einweisung_service.py        # UC-07, UC-08 (training)
│   ├── katalog_service.py           # UC-09 (inventory management)
│   ├── vormerkung_service.py        # UC-05 (reservations)
│   ├── verfuegbarkeit_service.py    # UC-10 (availability check)
│   └── audit_retention_service.py   # Maintenance (audit cleanup)
│
├── adapters/
│   ├── persistence/                 # Repository implementations (SQLite)
│   │   ├── sqlite_*.py              # 8 concrete repository adapters
│   │   └── schema.sql               # Database schema (CREATE TABLE…)
│   ├── rest/                        # HTTP/REST adapter
│   │   ├── app.py                   # FastAPI endpoint routing
│   │   ├── schemas.py               # Pydantic request/response models
│   │   ├── rollen.py                # Role-based access control
│   │   └── static/                  # Frontend (minimal)
│   └── system_clock.py              # SystemClock adapter (Clock port)
│
└── __init__.py
```

---

## 7. Technology & Infrastructure

### 7.1 Framework Stack
- **Language**: Python 3.11+
- **REST Framework**: FastAPI 0.115+
- **Database**: SQLite (single file, no external services)
- **Validation**: Pydantic 2.7+
- **CLI Framework**: Typer 0.12+
- **Testing**: Pytest 8.0+ with Hypothesis 6.100+

### 7.2 Architectural Patterns

| Pattern | Location | Purpose |
|---------|----------|---------|
| **Hexagonal Architecture** | ports/ + adapters/ | Decouple domain from infrastructure |
| **Protocol/Interface** | ports/*.py | Language-agnostic port contracts |
| **Repository** | adapters/persistence/ | Abstract data access |
| **Application Service** | anwendungskern/*.py | Orchestrate use cases |
| **Value Object** | domain/*.py (non-aggregates) | Immutable domain values |
| **Aggregate** | domain/*.py (with state) | Transaction boundaries |
| **State Machine** | domain/*Zustand enums | Entity lifecycle |
| **Transaction Script** | adapters/rest/app.py | REST endpoint handlers |
| **Adapter** | adapters/ | Cross-boundary translation |

### 7.3 Data Consistency Mechanisms

#### Database-Level (ADR-007, ADR-009)
1. **Unique Partial Index** (ausleihe.py schema):
   ```sql
   CREATE UNIQUE INDEX ux_ausleihe_aktiv_je_gegenstand
       ON ausleihe (gegenstand_id)
       WHERE zustand = 'aktiv'
   ```
   Prevents two simultaneous active loans for same equipment.

2. **Audit Log Immutability** (audit_log schema):
   ```sql
   CREATE TRIGGER trg_audit_log_no_update BEFORE UPDATE … SELECT RAISE(ABORT)
   CREATE TRIGGER trg_audit_log_no_delete BEFORE DELETE … SELECT RAISE(ABORT)
   ```
   Makes audit log append-only.

#### Application-Level
1. **BEGIN IMMEDIATE** in critical sections (ausleihe_service.py:206, verlust_service.py:86)
   - Acquires write lock before validation to prevent TOCTOU races

2. **Atomic Transactional Ports** (PruefabschlussRepository)
   - Multiple updates bundled in single transaction (line: pruefabschluss_repository.py)

3. **Snapshot-Based Kaution**
   - `Ausleihe.kaution_cent` frozen at checkout time (not dynamic)
   - Protects against category changes during active loans (BR-AUS-05)

---

## 8. Business Rules Traceability

| Rule | Location | Enforced By |
|------|----------|-------------|
| **BR-AUS-01** (equipment available or reserved for member) | ausleihe_service.py:122-130 | Domain logic + DB index |
| **BR-AUS-02** (max 3 loans per member) | ausleihe_service.py:135 | Application validation |
| **BR-AUS-03** (block overdue members) | ausleihe_service.py:163 | Application validation |
| **BR-AUS-04** (training required for restricted items) | ausleihe_service.py:137 | Application validation |
| **BR-AUS-06** (one extension max) | verlaengerung_service.py:138 | Application validation |
| **BR-AUS-07** (can't extend if overdue) | verlaengerung_service.py:125 | Application validation |
| **BR-KAT-01** (unique inventory numbers) | katalog_service.py:144 | DB primary key |
| **BR-KAT-02** (positive leihdauer/wartungsintervall) | katalog_service.py:59-68 | Application validation |
| **BR-KAT-03** (positive wiederbeschaffungswert) | katalog_service.py:71-75 | Application validation |
| **BR-KAT-04** (caution = 20% replacement value) | kaution.py:12-20 | Pure function (centralized) |
| **BR-KAU-02** (deduction ≤ deposit) | pruefung_service.py:78 | Application validation |
| **BR-EIN-01** (max 1 valid training per member/category) | einweisung_service.py:75 | DB unique index |
| **BR-EIN-02** (training valid until revoked) | einweisung.py:18-20 | Domain logic |
| **BR-VOR-01** (max 1 open reservation per member/category) | vormerkung_service.py:86 | DB unique index |
| **BR-VOR-02** (FIFO queue) | vormerkung_service.py:51-53 | Application sorting |
| **BR-VOR-03** (reserved equipment if queue exists) | wartung_service.py:105-107 | Application logic |
| **BR-WAR-01** (increment usage counter on inspection) | pruefung_service.py:148 | Application logic |
| **BR-WAR-02** (maintenance if usage ≥ interval) | pruefung_service.py:93-94 | Application logic |
| **BR-WAR-03** (reset counter after maintenance) | wartung_service.py:118 | Application logic |
| **BR-RUP-01** (equipment in_pruefung after return) | ausleihe_service.py:285 | Application logic |
| **BR-RUP-04** (loan abgeschlossen after inspection) | pruefung_service.py:193 | Application logic |
| **BR-RUP-05** (deduplicate damage by exact description) | pruefung_service.py:132-145 | Application logic |
| **BR-VER-01/02** (loss → abgeschlossen_verloren state) | verlust_service.py:102 | Application logic |
| **BR-VER-03** (lost equipment → ausgemustert) | verlust_service.py:115 | Application logic |
| **BR-KAU-03/04** (loss → 100% deposit seizure) | verlust_service.py:129 | Application logic |
| **BR-SPE-02** (member blocked if any loan overdue) | ausleihe_service.py:163 | Application validation |

---

## 9. Summary

The **Leihgut bounded context** is a **single, cohesive domain** that encompasses the complete business capability of equipment lending. It is internally well-organized into eight **subdomains**:

1. **Lending Lifecycle** (checkout, return, extension)
2. **Equipment Catalog** (inventory, categories, metadata)
3. **Security Deposits** (collateral calculation, tracking, refunds)
4. **Maintenance & Inspection** (damage tracking, maintenance scheduling)
5. **Training Requirements** (member certifications)
6. **Reservations** (FIFO queuing)
7. **Extension & Loss** (loan extension, loss declaration)
8. **Audit & Compliance** (immutable audit trail, retention policies)

**No external bounded contexts** are referenced; all communication flows through clearly-defined repository ports and the Clock abstraction. The architecture strictly adheres to **hexagonal principles** with clear separation between domain logic (pure, testable), application services (use case orchestration), and adapters (external system integration).

All 75+ business rules are traceable to specific code locations with enforcement distributed across domain entities (state machines), application services (validation), and database constraints (unique indices, triggers).

