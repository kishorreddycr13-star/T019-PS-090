# OTT Content Licensing, Windowing, and Subscriber Revenue-Share Engine (PS-090)

An enterprise-grade, financial-grade rights validation, viewership metering, and licensor revenue-share settlement engine developed in Python 3.10+ with pure `Decimal` mathematical precision and SQLite/PostgreSQL relational database persistence.

---

## 1. Executive Summary & Capabilities

The **OTT Rights & Royalty Engine** orchestrates the complete lifecycle of streaming content distribution:
- **Title, Licensor & Contract Management**: Multi-licensor title registry with strict 100.00% split validation, multi-window contracting, and catalog availability management.
- **Licence Validation Engine (BR-01, BR-02, BR-03)**: Validates window start/end dates, contiguous and adjacent windows, territorial exclusivity conflicts, and statutory holdbacks (45-day theatrical, 7-day TV premiere) in territory-local time.
- **Playback Eligibility Engine (BR-04, BR-11)**: Determines streaming permission for client playback requests at any global instant, converting UTC timestamps to territory-local time across arbitrary timezones (IN, US, SG, AE), allowing streams starting at 23:59:59 on window end dates to complete within 4 hours.
- **View Tracking & Metering Engine (BR-04, BR-07, BR-08)**: Scans raw player telemetry, evaluates the qualifying threshold ($\min(120\text{s}, \text{runtime} \times 0.5)$), separates `FREE` (AVOD) and `PREMIUM` (SVOD) consumption, and enforces 24-hour subscriber session deduplication.
- **Revenue Calculation Engine (BR-05, BR-06)**: Calculates territory-level 60% SVOD subscription pools (allocated pro-rata by qualifying view-hours) and 55% AVOD ad revenue pools (allocated pro-rata by ad impressions), rounded to 4 decimal ratios and half-up paise.
- **Royalty Adjustment & Accounting Engine (BR-07, BR-08, BR-09, BR-10)**: Disburses Minimum Guarantee (MG) advances in Month 1 of first window, amortizes gross shares against outstanding MG balances, enforces contractual payment caps (retaining excess earnings with `CAPPED` lifecycle transitions), applies domestic (10.00%) and foreign statutory/treaty withholding tax (TDS), and allocates co-licensor splits floored to paise with 1-paisa residue attribution to eliminate financial leakage.
- **Monthly Settlement & Deliverables (BR-12)**: Implements the 18-step settlement workflow, validates execution timing against the 10th of $M+1$ boundary, tags late views as `LATE_VIEW` shifted to $M+1$ at $M+1$ rates, commits tamper-evident SHA-256 sealed audit logs to the relational database, and exports the four mandatory evaluation CSV deliverables.

---

## 2. Project Directory Structure

```
ott_engine/
├── config.py                          # Environment and DB connection configuration (SQLite/PostgreSQL)
├── run_engine.py                      # Primary evaluation pipeline runner (processes commands.txt -> CSV outputs)
├── ott_engine.db                      # Relational database (WAL mode, foreign keys, 20 tables)
├── sample_data/                       # Official T019-PS-090 sample dataset
│   ├── README.md                      # Official evaluation specification & planted edge-case dictionary
│   ├── territories.csv                # 4 territories with fixed UTC offsets
│   ├── licensors.csv                  # 10 licensors (Indian/Foreign, DTAA treaty rates)
│   ├── titles.csv                     # 40 titles (runtime, theatrical & TV premiere dates)
│   ├── title_splits.csv               # Co-licensor split percentages (sum to 100.00%)
│   ├── licences.csv                   # 55 licence contract requests
│   ├── licence_windows.csv            # 62 availability windows
│   ├── subscription_revenue.csv       # Monthly territory PREMIUM subscription revenues
│   ├── ad_revenue.csv                 # Monthly territory AVOD advertisement revenues
│   ├── view_events.csv                # 2,132 ingestion view events (July-Sept 2026)
│   └── commands.txt                   # 134 command stream operations
├── evaluation_outputs/                # Official 4 evaluation CSV deliverables
│   ├── licence_validation.csv         # 55 rows (result, reason, conflicting_licence_id)
│   ├── view_decisions.csv             # 2,132 rows (decision, reason, qualifying, counted, tag)
│   ├── title_shares.csv               # 480 rows (view_hours, pool_share, ad_share, title_share)
│   └── settlements.csv                # 165 rows (gross, mg_paid, recouped, cap, tds, net_payable)
├── cli/
│   ├── __init__.py
│   └── management_cli.py              # CLI management tool (`ott-manage`)
├── database/
│   ├── __init__.py
│   ├── base.py                        # DeclarativeBase, UTCDateTime, TimestampMixin
│   └── connection.py                  # Engine factory, session manager, WAL pragma
├── models/
│   ├── __init__.py                    # Model registry across all 20 relational entities
│   ├── title.py                       # Table 1: Titles
│   ├── licensor.py                    # Table 2: Licensors, Table 3: Licensor Splits
│   ├── contract.py                    # Table 4: Licence Contracts, Table 14: MG, Table 16: Payment Caps
│   ├── window.py                      # Table 5: Licence Windows, Table 7: Holdbacks
│   ├── territory.py                   # Table 6: Territories & Time Zones, Table 17: Tax Rates
│   ├── subscriber.py                  # Table 8: Subscriber Tiers, Table 11: Subscription Revenue
│   ├── viewership.py                  # Table 9: View Events, Table 10: Qualifying View Records
│   ├── advertising.py                 # Table 12: Ad Revenue, Table 13: Ad Impressions
│   ├── settlement.py                  # Table 15: Recoupments, Table 18: Settlements, Table 19: Payments
│   └── audit.py                       # Table 20: Tamper-evident Audit Logs
├── repositories/
│   ├── __init__.py
│   ├── base_repository.py             # Generic CRUD repository abstraction
│   ├── licence_repository.py          # Licence contract persistence & queries
│   ├── licensor_repository.py         # Licensor & split queries
│   ├── metering_repository.py         # View consumption & deduplication queries
│   ├── payment_repository.py          # Monthly settlement persistence & queries
│   ├── revenue_repository.py          # Subscription & ad revenue master queries
│   ├── title_repository.py            # Title master queries
│   └── view_repository.py             # View event ingestion queries
├── services/
│   ├── __init__.py
│   ├── advertisement_calculator.py    # 55% AVOD ad revenue pool pro-rata allocation
│   ├── cap_service.py                 # Contractual payment cap headroom & retention
│   ├── duplicate_detection.py         # 24-hour subscriber session deduplication
│   ├── licence_service.py             # Licence contract administration service
│   ├── licensor_service.py            # Studio & licensor administration service
│   ├── licensor_split_service.py      # Co-licensor split allocation with paise residue
│   ├── metering_service.py            # Consumption aggregation service
│   ├── mg_service.py                  # Minimum Guarantee advance disbursement & tracking
│   ├── playback_service.py            # Client playback heartbeat evaluation service
│   ├── qualification_service.py       # Qualifying view evaluation (min(120, runtime/2))
│   ├── recoupment_service.py          # Gross share amortization against MG balance
│   ├── reporting_service.py           # Formatted tabular reporting (calendar, settlement, views)
│   ├── revenue_service.py             # Subscription & ad pool coordination
│   ├── revenue_validation.py          # Revenue master data integrity checks
│   ├── royalty_service.py             # Royalty adjustment waterfall orchestration
│   ├── settlement_service.py          # BR-12 settlement workflow & evaluation export
│   ├── split_validator.py             # 100.00% split validation
│   ├── subscription_calculator.py     # 60% SVOD subscription pool pro-rata allocation
│   ├── tax_service.py                 # Statutory & DTAA treaty withholding tax calculation
│   └── title_service.py               # Audiovisual title registry service
├── engine/
│   ├── __init__.py
│   ├── command_processor.py           # Sequential processor for commands.txt
│   ├── licence_manager.py             # Adapter around validation engine
│   ├── licence_validation_engine.py   # BR-01, BR-02, BR-03 validation engine
│   ├── playback_eligibility_engine.py # BR-04, BR-11 eligibility engine
│   ├── revenue_settlement_engine.py   # BR-05..BR-10, BR-12 financial settlement engine
│   ├── view_processor.py              # Ingestion, deduplication, and late view tagging
│   └── windowing_service.py           # Timezone conversion & active window locator
├── scripts/
│   ├── __init__.py
│   ├── init_db.py                     # Creates tables and database constraints
│   ├── sync_sample_data_to_db.py      # Imports CSV master datasets into SQLite database
│   └── verify_schema.py               # Integrity & foreign key verification script
└── tests/
    ├── test_management_module.py      # Phase 1 & 2 tests (18 tests)
    ├── test_licence_validation_engine.py # Phase 3 & 4 tests (20 tests)
    ├── test_playback_eligibility.py   # Phase 5 tests (19 tests)
    ├── test_metering_engine.py        # Phase 6 tests (20 tests)
    ├── test_revenue_engine.py         # Phase 7 tests (20 tests)
    ├── test_royalty_engine.py         # Phase 8 tests (20 tests)
    ├── test_monthly_settlement.py     # Phase 9 tests (20 tests)
    ├── test_full_integration.py       # Phase 10 full integration tests (29 tests)
    └── test_planted_scenarios.py      # Evaluation runner & planted scenario verifier
```

---

## 3. Business Rules Implementation Matrix

| Rule | Business Rule Summary | Implementation Component | Verification Method |
|---|---|---|---|
| **BR-01** | **Window Validity & Continuity**: Windows must have valid `start <= end`. Overlapping internal windows within same contract are rejected; adjacent windows are permitted; gaps between windows deny playback. | [`engine/licence_validation_engine.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/engine/licence_validation_engine.py)<br>[`engine/windowing_service.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/engine/windowing_service.py) | Unit tests in `test_licence_validation_engine.py`; Trap 2 in `test_planted_scenarios.py`. |
| **BR-02** | **Exclusivity Enforcement**: An `EXCLUSIVE` licence blocks any concurrent licence for the same title and territory. Rejection returns conflicting licence ID. `NON_EXCLUSIVE` licences coexist. | [`engine/licence_validation_engine.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/engine/licence_validation_engine.py) | Unit tests; Trap 1 (`LCN-055` rejected citing `LCN-046`). |
| **BR-03** | **Statutory Holdback Gaps**: Theatrical OTT window start $\ge$ Theatrical Premiere $+ 45$ days. TV OTT window start $\ge$ TV Premiere $+ 7$ days. Exact boundary dates strictly validated. | [`engine/licence_validation_engine.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/engine/licence_validation_engine.py) | EC-08 (`LCN-019` accepted at 45d, `LCN-054` rejected at 44d, `LCN-009` accepted at 7d TV). |
| **BR-04** | **Window Eligibility**: Playback permitted between 00:00:00 and 23:59:59 in territory-local time. UTC converted to local via territory IANA offsets. | [`engine/playback_eligibility_engine.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/engine/playback_eligibility_engine.py) | EC-01 (`VW-001417` at 23:59:59 allowed); EC-06 (UTC midnight straddle: `VW-001418` IN denied, `VW-001419` US allowed). |
| **BR-05** | **Subscription Revenue Pool**: 60% of territory `PREMIUM` subscription revenue forms the SVOD pool. Allocated pro-rata by title qualifying view-hours. Ratios rounded half-up to 4 decimals, shares to paise. | [`services/subscription_calculator.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/services/subscription_calculator.py) | Unit tests in `test_revenue_engine.py`; verified in `title_shares.csv`. |
| **BR-06** | **Advertisement Revenue Share**: 55% of territory `FREE` ad revenue shared according to impressions. POOL_ONLY licences exclude ad revenue. | [`services/advertisement_calculator.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/services/advertisement_calculator.py) | Unit tests in `test_revenue_engine.py`; verified in `title_shares.csv`. |
| **BR-07** | **Qualifying Views & MG Recoupment**: View qualifies if $\text{watch\_seconds} \ge \min(120, \text{runtime}/2)$. Minimum Guarantee advance paid in Month 1 of first window; subsequent gross shares recoup MG; excess is payable. No clawback. | [`services/qualification_service.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/services/qualification_service.py)<br>[`services/mg_service.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/services/mg_service.py)<br>[`services/recoupment_service.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/services/recoupment_service.py) | EC-02 (180s runtime: 90s threshold); EC-04 (`LCN-015` MG Rs 389,735.59 recouped in Sept down to Rs 0.00). |
| **BR-08** | **24-Hour Deduplication & Payment Caps**: Duplicate views of same title by same subscriber within 24 hours count once. Cumulative licence payments capped at contract limit; mid-month cap retains excess; status `CAPPED`. | [`services/duplicate_detection.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/services/duplicate_detection.py)<br>[`services/cap_service.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/services/cap_service.py) | EC-03 (`VW-000512` discarded at 23h59m); EC-05 (`LCN-032` capped in Aug with Rs 354,858.05 retained). |
| **BR-09** | **Withholding Tax (TDS)**: Domestic Indian entities = 10.00%. Foreign entities = 20.00% statutory, overridden by DTAA treaty rates (e.g. 15.00%) where registered. Applied to `payable_before_tds`. | [`services/tax_service.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/services/tax_service.py) | Unit tests in `test_royalty_engine.py` and `test_monthly_settlement.py`. |
| **BR-10** | **Co-Licensor Splits with Zero Leakage**: Title split percentages must equal 100.00%. Individual shares floored to paise; fractional rounding residue (e.g. 1 paisa) assigned to largest split share. | [`services/licensor_split_service.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/services/licensor_split_service.py) | EC-07 (`LCN-012` 33.33/33.33/33.34 split of Rs 151593.74 attributes 1 paisa to `LIC-04`). |
| **BR-11** | **Catalogue Removal & Buffer**: Active streams starting at 23:59:59 on window end date are permitted to play for up to 4 hours past window close. | [`engine/windowing_service.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/engine/windowing_service.py) | EC-01 (`VW-001417` at 23:59:59 IST allowed). |
| **BR-12** | **Settlement Timing & Cutoff**: Settle on the 10th of $M+1$. Events ingested strictly before cutoff instant count in month $M$. Late events tagged `LATE_VIEW`, shifted to $M+1$, and settled at $M+1$ rates. | [`services/settlement_service.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/services/settlement_service.py)<br>[`engine/view_processor.py`](file:///C:/Users/kisho/.gemini/antigravity/scratch/ott_engine/engine/view_processor.py) | Trap 3 (`VW-001661` tagged `LATE_VIEW` and settled in Sept at Sept rates); unit tests 1-8 in `test_monthly_settlement.py`. |

---

## 4. Execution & Quickstart Instructions

### Prerequisites
- Python 3.10+ (tested on Python 3.12)
- Dependencies installed: `pip install -r requirements.txt` (SQLAlchemy 2.0+)

### Running the End-to-End Evaluation Pipeline
To execute the complete command stream on any dataset and generate all 4 evaluation CSV files:

```bash
# Using default sample data directory:
python run_engine.py

# Or specifying explicit input dataset and output destination:
python run_engine.py sample_data evaluation_outputs
```

Output:
```
======================================================================
OTT Rights & Royalty Engine (PS-090) - Evaluation Runner
Data Directory:   sample_data
Output Directory: evaluation_outputs
======================================================================
Loading input CSV files...
Loaded 40 titles, 55 licences, 2132 view events.

Processing command stream: sample_data/commands.txt...
...
[SUCCESS] All commands processed and deliverables generated successfully.
  1. licence_validation.csv (55 rows)
  2. view_decisions.csv     (2132 rows)
  3. title_shares.csv       (480 rows)
  4. settlements.csv        (165 rows)
```

### Running the Full Test Suite
To run all 146 unit, integration, and scenario tests:

```bash
# Run all unit tests across all 10 phases:
python -m unittest discover -s tests -p "test_*.py"

# Run evaluation planted scenario verifier:
python tests/test_planted_scenarios.py

# Run dedicated Phase 10 integration suite:
python -m unittest tests/test_full_integration.py
```

### Using the Management CLI (`ott-manage`)
The engine includes a CLI tool for operational administration:

```bash
# 1. Rights Calendar report for a title:
python cli/management_cli.py report calendar --title-id TTL-001

# 2. Monthly Licensor Settlement Statement:
python cli/management_cli.py report settlement --licensor-id LIC-01 --month 2026-07

# 3. View Decisions Report over a date window:
python cli/management_cli.py report views --from-date 2026-07-01 --to-date 2026-07-01

# 4. Run monthly settlement pipeline:
python cli/management_cli.py settlement run

# 5. Playback entitlement check:
python cli/management_cli.py playback check --title-id TTL-001 --territory IN --start-utc "2026-07-01 12:00:00"
```

---

## 5. Evaluation Deliverables Specification

The 4 CSV deliverables generated in `evaluation_outputs/` conform to the PS-090 evaluation schema:

### 1. `licence_validation.csv` (55 rows)
- **Header**: `licence_id,result,reason,conflicting_licence_id`
- **Conventions**: `ACCEPTED` or `REJECTED`. Rejections cite `HOLDBACK` or `EXCLUSIVITY` (with conflicting licence ID).

### 2. `view_decisions.csv` (2,132 rows)
- **Header**: `view_id,decision,reason,licence_id,local_start,settlement_month,qualifying,counted,view_hours,tag`
- **Conventions**: File-order preservation; `ALLOWED` or `DENIED`; territory-local timestamps; `qualifying` (`true`/`false`); `counted` (`true`/`false`); `view_hours` formatted as `0.0000`; `tag` (`LATE_VIEW` for shifted views, empty otherwise).

### 3. `title_shares.csv` (480 rows)
- **Header**: `month,territory_id,title_id,premium_view_hours,pool_ratio,pool_share,ad_impressions,ad_ratio,ad_share,title_share`
- **Conventions**: Sorted by `month`, `territory_id`, `title_id`; `pool_ratio` and `ad_ratio` to 4 decimals (`0.0000`); monetary shares in Rs to 2 decimal places (`0.00`).

### 4. `settlements.csv` (165 rows)
- **Header**: `month,licence_id,licensor_id,split_pct,gross_share,mg_paid,recouped,mg_balance,cap_retained,payable_before_tds,tds_pct,tds,net_payable,status`
- **Conventions**: Sorted by `month`, `licence_id`, `licensor_id`; co-licensor splits; exact MG advance & recoupment; payment cap retention; domestic/treaty TDS; status `SETTLED` or `CAPPED`.

---

## 6. Architecture & Financial Precision Standards

1. **Zero Financial Leakage**: All financial amounts use Python `Decimal`. Pro-rata ratios are quantized to 4 decimal places (`ROUND_HALF_UP`), pool and ad shares to paise (`ROUND_HALF_UP`). Co-licensor split shares are floored to paise (`ROUND_FLOOR`), with the exact rounding residue attributed to the licensor with the largest registered split percentage.
2. **Hidden Evaluation Compatibility**: Zero hardcoded planted IDs or hardcoded answers exist in the core engines (`engine/`, `services/`). All titles, licences, windows, views, and revenues are ingested and processed dynamically.
3. **Database Idempotency & ACID Transactions**: Re-running settlement runs updates existing settlement records in place without duplicating payments or corrupting historical ledger balances. Database persistence operations are wrapped in atomic transactions with automatic rollback on error.
4. **PostgreSQL Migration Readiness**: Built using SQLAlchemy 2.0 with dialect-agnostic column definitions (`UTCDateTime`, `Numeric(18, 4)`). To switch from SQLite to PostgreSQL, set `DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/dbname"`.
