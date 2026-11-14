# PS-090 – OTT Content Licensing, Windowing and Subscriber Revenue-Share Engine — Sample Data Pack

Prepared by 10 SECONDS for Team T019.

## Files

| File | What it holds | Row count |
|---|---|---|
| `territories.csv` | 4 territories with fixed UTC offsets (minutes) | 4 data rows |
| `licensors.csv` | 10 licensors (Indian / foreign, treaty TDS rate where registered) | 10 data rows |
| `titles.csv` | 40 titles with runtime and theatrical / TV premiere dates | 40 data rows |
| `title_splits.csv` | Co-licensor split percentages (titles with more than one licensor) | 3 data rows |
| `licences.csv` | 55 licence requests (validated by CREATE_LICENCE in file order) | 55 data rows |
| `licence_windows.csv` | Availability windows per licence (one or more) | 62 data rows |
| `subscription_revenue.csv` | PREMIUM subscription revenue per month and territory | 12 data rows |
| `ad_revenue.csv` | Ad revenue per month and territory | 12 data rows |
| `view_events.csv` | View events Jul-Sep 2026 in ingestion order | 2132 data rows |
| `commands.txt` | Licence creation, ingestion checkpoints, settlement runs on the 10th and print requests | 132 command lines (excluding comments) |

Volumes in this sample are reduced for email delivery; the hidden evaluation set is larger and uses the same schema.

Row numbers quoted below are 1-based data-row numbers (the header is row 0). Line numbers for `commands.txt` are physical line numbers including comment lines.

## Column reference

Conventions: dates `YYYY-MM-DD`; timestamps `YYYY-MM-DD HH:MM:SS` (24h, IST, no timezone suffix); money in Rs as plain decimals with 2 places (no commas, no symbol); percentages as plain numbers (12.5 means 12.5%); booleans `true`/`false`; IDs uppercase with a fixed prefix. An empty cell means "not applicable" and only occurs in columns whose notes say so.

### `territories.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| territory_id | string | — | IN, AE, SG, US | — |
| territory_name | string | — | — | — |
| utc_offset_minutes | int | minutes | — | local = UTC + offset (fixed, no DST in this pack) |

### `licensors.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| licensor_id | string | LIC-nn | — | — |
| licensor_name | string | — | — | — |
| country | string | — | — | — |
| is_indian | bool | — | — | TDS 10% if true, else 20% unless a treaty rate is given |
| treaty_tds_pct | decimal | % | — | empty = no treaty rate |

### `titles.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| title_id | string | TTL-nnn | — | — |
| title_name | string | — | — | — |
| content_type | enum | — | FILM, SERIES_EPISODE, DOCUMENTARY, MUSIC_VIDEO | — |
| runtime_seconds | int | s | — | qualifying view = min(120, 50% of runtime) seconds |
| theatrical_premiere | date | — | — | OTT window start >= premiere + 45 days |
| tv_premiere | date | — | — | OTT window start >= premiere + 7 days |

### `title_splits.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| title_id | string | — | titles.csv | — |
| licensor_id | string | — | licensors.csv | — |
| split_pct | decimal | % | — | sums to 100.00 per title |

### `licences.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| licence_id | string | LCN-nnn | — | creation order = id order |
| title_id | string | — | titles.csv | — |
| licensor_id | string | — | licensors.csv | lead licensor (co-licensed titles settle by title_splits.csv) |
| territory_id | string | — | territories.csv | — |
| exclusivity | enum | — | EXCLUSIVE, NON_EXCLUSIVE | — |
| revenue_share_type | enum | — | POOL_AND_AD, POOL_ONLY | POOL_ONLY licences get no ad share |
| mg_amount | decimal | Rs | — | 0.00 = no minimum guarantee |
| cap_amount | decimal | Rs | — | 0.00 = no cap |

### `licence_windows.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| licence_id | string | — | licences.csv | — |
| window_no | int | — | — | — |
| window_start | date | local | — | playable from 00:00:00 local |
| window_end | date | local | — | playable until 23:59:59 local |

### `subscription_revenue.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| month | string | YYYY-MM | — | — |
| territory_id | string | — | territories.csv | — |
| premium_revenue | decimal | Rs | — | 60% forms the pool |

### `ad_revenue.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| month | string | YYYY-MM | — | — |
| territory_id | string | — | territories.csv | — |
| ad_revenue | decimal | Rs | — | 55% shared by impressions |

### `view_events.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| view_id | string | VW-nnnnnn | — | numbered in ingestion order |
| subscriber_id | string | — | — | — |
| tier | enum | — | FREE, PREMIUM | — |
| territory_id | string | — | territories.csv | — |
| title_id | string | — | titles.csv | — |
| start_utc | timestamp | UTC | — | convert to local time for window and month |
| watch_seconds | int | s | — | — |
| ad_impressions | int | — | — | FREE views only |
| ingested_utc | timestamp | UTC | — | file sorted by this |

## Command file format

`commands.txt` holds one command per line in the form `COMMAND_NAME|arg1|arg2|...`. Commands must be processed strictly in file order. Lines starting with `#` are comments and blank lines are ignored. An empty argument (two pipes in a row) means "not supplied". Every command used in this pack:

| Command | Arguments (in order) | Meaning |
|---|---|---|
| `CREATE_LICENCE` | `licence_id` | Validate holdback and exclusivity against licences already ACCEPTED; ACCEPTED or REJECTED (with conflicting licence id) |
| `INGEST_VIEWS_UNTIL` | `timestamp` | Decide every view ingested before this instant (ALLOWED / DENIED, qualifying, de-duplication) |
| `SETTLE` | `YYYY-MM|run_ts` | Monthly settlement per licence and licensor (late views go to the next month) |
| `PRINT_RIGHTS_CALENDAR` | `title_id` | Windows per territory and licence |
| `PRINT_SETTLEMENT` | `licensor_id|YYYY-MM` | Settlement statement |
| `PRINT_VIEW_DECISIONS` | `from_date|to_date` | View decisions |

## Planted scenarios

Every edge case in the brief, mapped to the exact record where it occurs, followed by extra traps.

- **EC-01 View starting at 23:59:59 local time on the window end day**
  - VW-001417 starts 2026-08-31 18:29:59 UTC = 23:59:59 IST on the last day of LCN-028's IN window -> ALLOWED (the 90-minute stream may run past the window end, up to 4 h) — `view_events.csv VW-001417 (row 1417); licences.csv LCN-028 (row 28)`
- **EC-02 Title with runtime 180 seconds - qualifying threshold is 90 seconds not 120**
  - VW-000997: title TTL-038 has runtime 180 s -> threshold min(120, 50% x 180) = 90 s: the 95-second view qualifies, VW-000999 (85 s) does not — `view_events.csv VW-000997 (row 997); view_events.csv VW-000999 (row 999); titles.csv TTL-038 (row 38)`
- **EC-03 Same subscriber watching the title at 10:00 and 09:59 next day - counts once**
  - VW-000491 at 2026-07-21 10:00 IST and VW-000512 at 2026-07-22 09:59 IST: same subscriber, same title, 23 h 59 min apart -> counted once (the second view adds no view-hours) — `view_events.csv VW-000491 (row 491); view_events.csv VW-000512 (row 512)`
- **EC-04 MG recouped exactly in the final month of the window**
  - LCN-015 (TTL-011, IN, window 2026-07-01 .. 2026-09-30, MG Rs 389735.59): monthly pool shares 185069.73, 79284.27, 125381.59 add up exactly to the MG -> MG paid in July, nothing in August, and the MG is recouped exactly in September, the final month of the window (September payment 0.00) — `licences.csv LCN-015 (row 15)`
- **EC-05 Cap reached mid-month - partial share paid up to cap**
  - LCN-032 (TTL-027, IN, no MG, cap Rs 765178.48): July share 556769.78 is paid in full; the August share 563266.75 reaches the cap -> only 208408.70 is paid, the licence is tagged CAPPED and the September share is retained by the platform — `licences.csv LCN-032 (row 32)`
- **EC-06 Two territories with different local times straddling UTC midnight**
  - LCN-028 (IN, UTC+05:30) and LCN-010 (US, UTC-04:00) both end 2026-08-31 local; views VW-001418 and VW-001419 start at the same instant 2026-08-31 22:30 UTC = 2026-09-01 04:00 IST (after the IN window -> DENIED) and 2026-08-31 18:30 EDT (inside the US window -> ALLOWED) — `licences.csv LCN-028 (row 28); licences.csv LCN-010 (row 10); view_events.csv VW-001418 (row 1418); view_events.csv VW-001419 (row 1419)`
- **EC-07 Co-licensor split 33.33/33.33/33.34 with 1 paisa residue**
  - LCN-012 (TTL-008, SG) is co-licensed 33.33 / 33.33 / 33.34 (title_splits.csv); its July share is Rs 151593.74 -> floored parts 50526.19 + 50526.19 + 50541.35 leave a residue of Rs 0.01 that goes to LIC-04 (33.34%, the largest share) — `licences.csv LCN-012 (row 12); subscription_revenue.csv 2026-07 (row 3)`
- **EC-08 Licence creation whose window starts on the 45th day after theatrical premiere**
  - LCN-019: theatrical premiere 2026-05-22 + 45 days = 2026-07-06 = window start -> ACCEPTED. Contrast LCN-054: premiere 2026-05-29, window starts 2026-07-12 = premiere + 44 days -> REJECTED (holdback); LCN-009: TV premiere 2026-06-26 + 7 days = 2026-07-03 -> ACCEPTED — `licences.csv LCN-019 (row 19); licences.csv LCN-054 (row 54); licences.csv LCN-009 (row 9)`
- **Extra traps (not in the brief, but realistic):**
  - LCN-055 (NON_EXCLUSIVE) overlaps EXCLUSIVE licence LCN-046 for the same title and territory (US) -> REJECTED citing LCN-046 — `licences.csv LCN-055 (row 55); licences.csv LCN-046 (row 46)`
  - VW-001046: view on 2026-08-14 in the gap between LCN-017's two windows (ends 2026-07-31, restarts 2026-09-01) -> DENIED — `view_events.csv VW-001046 (row 1046); licences.csv LCN-017 (row 17)`
  - VW-001661: August view ingested 2026-09-11, after the August settlement run (2026-09-10 00:00 UTC) -> tagged LATE_VIEW and settled in September at September rates — `view_events.csv VW-001661 (row 1661)`

## What is NOT in this pack

Expected outputs are not provided for this set. Validate your engine with your own test suite against the rules in your brief (BR-01 … BR-nn). A separate hidden input set with the same schema will be used at final evaluation; outputs are compared field-for-field, so follow the column formats above exactly in your own output.

## Output format expected at evaluation

Produce these CSV files (header row, same conventions as above, rows sorted as stated). Where the brief is silent on a format detail the choice below is binding for evaluation.

### `licence_validation.csv`

One row per CREATE_LICENCE.

Columns, in order: `licence_id`, `result`, `reason`, `conflicting_licence_id`

### `view_decisions.csv`

One row per view, in file order.

Columns, in order: `view_id`, `decision`, `reason`, `licence_id`, `local_start`, `settlement_month`, `qualifying`, `counted`, `view_hours`, `tag`

### `title_shares.csv`

One row per title, territory and month.

Columns, in order: `month`, `territory_id`, `title_id`, `premium_view_hours`, `pool_ratio`, `pool_share`, `ad_impressions`, `ad_ratio`, `ad_share`, `title_share`

### `settlements.csv`

One row per licence and licensor per month.

Columns, in order: `month`, `licence_id`, `licensor_id`, `split_pct`, `gross_share`, `mg_paid`, `recouped`, `mg_balance`, `cap_retained`, `payable_before_tds`, `tds_pct`, `tds`, `net_payable`, `status`

Binding choices where the brief is silent: the settlement month of a view is its local start month; a view counts if watch_seconds >= min(120, runtime/2) and no counted view of the same subscriber and title started less than 24 h earlier; view-hours = watch_seconds / 3600. pool_ratio and ad_ratio are rounded half-up to 4 decimals, shares to paise. MG: paid in month 1 of the first window; every monthly gross share from month 1 is recouped against it and only the excess is paid. Co-licensor parts are floored to the paisa and the residue goes to the largest split. Overlapping NON_EXCLUSIVE licences of different licensors: views go to the licence created first. Revenue is in Rs for all territories.
