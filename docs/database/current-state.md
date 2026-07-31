# Current State

## Stack

- Application runtime: Python 3.11+.
- Organizer source of truth today: simplified SQLite database loaded by `sorting/reading_order.py`; legacy ordered JSON remains supported.
- Research/download source of truth today: SQLite `comic_runs`, `issues`, and `story_arcs`.
- Database stack: local SQLite.
- Migration framework: raw SQL schema file plus idempotent import scripts.

## Existing Data

The target database has SQLite tables for:

- `comic_runs`
- `issues`
- `story_arcs`

Current local counts after the 2026-07-31 Spider-affiliated limited-run expansion:

- `comic_runs`: 296
- `issues`: 1,250
- `story_arcs`: 1,250

The organizer reads SQLite directly when `reading_order_path` points to `.db`, `.sqlite`, or `.sqlite3`.

## Application Dependency

The organizer needs only ordered entries with:

- run
- volume
- issue
- position

The research workflow now needs only:

- comic run
- issue number
- issue release date
- comic run start date
- comic run end date
- universe hint
- lead character text
- story arc

## Risks

- Marvel blocks plain scripted HTTP for some pages, so rendered-page capture may be required.
- Story arcs are still placeholders for bulk-imported issues until arc/event research is performed.
- The simplified `UNIQUE(cand_id, issue_number)` constraint intentionally treats variants as non-reading duplicates, but it needs review for genuinely distinct same-number publications.
- The current live database may still be on the previous schema until `scripts/db_migrate_simplify_schema.py` can replace it while no DB editor has it locked.

## Assumptions

- This is a local project, not a production service.
- SQLite is sufficient for thousands of rows and avoids a server dependency.
- Existing JSON should remain importable/exportable during the transition.
