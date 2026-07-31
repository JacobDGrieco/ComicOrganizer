# Current State

## Stack

- Application runtime: Python 3.11+.
- Organizer source of truth today: simplified SQLite database loaded by `sorting/reading_order.py`; legacy ordered JSON remains supported.
- Research/download source of truth today: SQLite `comic_runs`, `issues`, and `story_arcs`.
- Database stack: local SQLite.
- Active database file: `database/database.db`.
- Migration framework: raw SQL schema file plus idempotent import scripts.

## Existing Data

The target database has SQLite tables for:

- `comic_runs`
- `issues`
- `story_arcs`

Current local counts after the 2026-07-31 P0/P1/P2/P3 Marvel Fandom issue import and Fandom story-arc backfill:

- `comic_runs`: 296
- `issues`: 3,803
- `story_arcs`: 4,116
- issues assigned to canonical Fandom event/story-arc rows: 1,440
- issues with explicit Fandom page `sort_order`: 820
- issues still using local placeholder arcs: 2,363

Current story-arc ID namespaces:

- `FANDOM-EVENT-*`: 82 canonical Fandom event rows.
- `FANDOM-STORY-*`: 231 canonical Fandom story-arc rows.
- `LOCAL-ARC-*`: 3,803 local fallback placeholder rows.

Current issue ID namespace:

- `FANDOM-ISS-*`: 3,803 issue rows.

All P0, P1, P2, and P3 runs now have issue rows. `LOCAL-ARC-*` placeholder arcs remain where Marvel Fandom issue pages did not expose an `EventN` or `StoryArcN` field, or where a local issue could not be matched to a Fandom issue page.

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
- issue sort order within a Fandom event/story-arc page when available
- comic run start date
- comic run end date
- universe hint
- lead character text
- story arc

## Risks

- Marvel blocks plain scripted HTTP for some pages, so rendered-page capture may be required.
- Fandom volume pages include solicited future issues for some current runs; imports should be capped by release date when the local catalog should contain only released comics.
- Some story arcs are still placeholders for issues that have no detected Marvel Fandom event/story-arc metadata.
- The simplified `UNIQUE(cand_id, issue_number)` constraint intentionally treats variants as non-reading duplicates, but it needs review for genuinely distinct same-number publications.
- The current live database may still be on the previous schema until `scripts/db_migrate_simplify_schema.py` can replace it while no DB editor has it locked.

## Assumptions

- This is a local project, not a production service.
- SQLite is sufficient for thousands of rows and avoids a server dependency.
- Existing JSON should remain importable/exportable during the transition.
