# SQLite Proposal

## Existing Design

Research/download data was moved from JSON into a local SQLite database. The current SQLite database still contains an over-modeled research schema with old run rows, candidate run rows, sources, universes, characters, source join tables, review items, and issue character joins.

## Proposed Design

Simplify the working database to the three tables needed for download collection and reading-order sorting:

- `comic_runs`
- `issues`
- `story_arcs`

The existing `comic_run_candidates` table becomes the new `comic_runs` table. The old `comic_runs` table is dropped after its `SER-*` IDs are mapped to candidate IDs for existing issue rows.

The organizer continues to read SQLite from `reading_order_path`, but issue rows now reference `issues.cand_id` instead of `issues.run_id`.

## Requirement

The project is now optimized for practical download collection and sorting. The extra research tables are not needed for the current workflow and slow down schema changes.

## Benefit

- One canonical run table.
- Fewer joins for reading-order export.
- Existing issue rows preserved under `CAND-*` run IDs.
- Easier Marvel official-site scraping and staging work.
- Lower maintenance cost while the project is still moving quickly.

## Compatibility

This is a breaking SQLite schema change. Legacy JSON remains readable, but scripts that use the SQLite schema must be updated at the same time.

## Data Transformation

1. Back up `database.db`.
2. Create a new simplified database from `database/schema.sql`.
3. Copy `comic_run_candidates` into the new `comic_runs`.
4. Copy `story_arcs` without `universe_id`.
5. Copy `issues`, converting `run_id` to `cand_id` via `comic_run_candidates.local_run_id`.
6. Drop old tables by replacing the database with the migrated copy.

Rows that cannot map from old `SER-*` IDs to candidate IDs must fail the migration rather than being silently discarded.

## Verification

Run:

```powershell
python scripts\db_migrate_simplify_schema.py --db database.db
python scripts\db_validate.py --db database.db
python scripts\db_export_reading_order.py --db database.db
python -m unittest discover -s tests
```

## Rollback

Restore the timestamped backup written next to `database.db`.

## Classification

Breaking, data migration required, explicitly requested by the user.
