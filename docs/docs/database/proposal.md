# SQLite Proposal

## Existing Design

The working SQLite database has three catalog tables:

- `comic_runs`
- `issues`
- `story_arcs`

Every imported issue currently points at a story arc, but most imported rows still use issue-level placeholder arcs. That preserves ordering by release date, but it does not group crossover issues into the Marvel Fandom event or story-arc reading order.

The `issues` table also has no field for an explicit within-arc ordering value.

## Proposed Design

Add a nullable `issues.sort_order` column and backfill story-arc assignments from Marvel Fandom issue pages.

The backfill uses Marvel Fandom issue-page template fields in this priority order:

1. `Event1`, `Event2`, and later numbered event fields.
2. `StoryArc1`, `StoryArc2`, and later numbered story-arc fields.
3. Existing placeholder story arc when no Fandom event or story arc is found.

When an issue lists multiple events or story arcs, select the linked page whose event/story-arc page starts first. The first date is estimated from ordered `PartN` fields, explicit `Reading Order:` entries, or ordered comic links on the Fandom page, matched back to issue release dates already in SQLite.

`sort_order` stores the issue's position on the selected Fandom event/story-arc page when that order is available. Rows without a reliable page order keep `sort_order = NULL` and continue to sort by release date.

## Requirement

Story arcs are used to blend release-date reading with run-start ordering. Spider-Man crossover events often jump across several runs, so the database needs the event/story-arc grouping and exact within-arc order when Fandom provides it.

## Benefit

- Cross-run issues can be grouped by event/story arc instead of isolated placeholder arcs.
- Reading order can prefer curated Fandom order inside a story arc.
- Existing release-date behavior remains as a fallback.
- The backfill is idempotent and can be rerun as issue-page matching improves.

## Compatibility

This is an additive SQLite schema change. Existing code that ignores `issues.sort_order` remains compatible. The organizer's SQLite reader should prefer `sort_order` only when it is present.

## Data Transformation

1. Back up `databases/spider-man.db`.
2. Add `issues.sort_order INTEGER` when missing.
3. Add an index for story-arc ordering.
4. Fetch Marvel Fandom issue pages for local issues.
5. Upsert canonical Fandom event/story-arc rows into `story_arcs`.
6. Update matching `issues.story_arc_id` and `issues.sort_order`.
7. Leave unresolved issues attached to their current placeholder story arc with `sort_order = NULL`.

## Verification

Run:

```powershell
python scripts\db_validate.py --db databases/spider-man.db
python scripts\db_backfill_fandom_story_arcs.py --db databases/spider-man.db --dry-run --limit 25
python scripts\db_backfill_fandom_story_arcs.py --db databases/spider-man.db
python scripts\db_validate.py --db databases/spider-man.db
python -m py_compile scripts\db_backfill_fandom_story_arcs.py scripts\db_validate.py sorting\reading_order.py
python -m unittest discover -s tests
```

## Rollback

Restore the backup written next to `databases/spider-man.db` before the backfill.

## Classification

Additive schema change with data backfill, requested by the user.

---

# Legacy Story-Arc ID Cleanup

## Existing Design

The story-arc backfill introduced canonical Fandom grouping IDs:

- `FANDOM-EVENT-*`
- `FANDOM-STORY-*`

The database still contains older placeholder IDs created by earlier import stages:

- `ARC-*`
- `GCD-ARC-*`
- `MM-ARC-*`
- `FANDOM-ARC-*`

These rows are mostly single-issue fallback arcs. Some are still referenced by issues, and some are now orphaned because their issues were moved to canonical Fandom event/story-arc rows.

## Proposed Design

Normalize legacy placeholder rows to `LOCAL-ARC-*`.

If a legacy row can be mapped to an existing canonical Fandom event/story-arc row by exact normalized title, merge the issue references into that canonical row. Otherwise, preserve the row data under a deterministic local placeholder ID:

```text
LOCAL-ARC-<story-arc-title-slug>[-<start-date>][-<legacy-id>]
```

The active Marvel Fandom volume importer should also create future placeholder arcs with the `LOCAL-ARC-*` prefix instead of `FANDOM-ARC-*`.

## Requirement

The arc ID namespace should communicate data confidence:

- `FANDOM-EVENT-*`: real event grouping found on Marvel Fandom.
- `FANDOM-STORY-*`: real story-arc grouping found on Marvel Fandom.
- `LOCAL-ARC-*`: local fallback placeholder used until a better grouping is found.

## Evidence

Current local counts before cleanup:

- `ARC-*`: 4 story arcs, 4 referenced issues.
- `GCD-ARC-*`: 10 story arcs, 10 referenced issues.
- `MM-ARC-*`: 1,236 story arcs, 749 referenced issues.
- `FANDOM-ARC-*`: 2,553 story arcs, 1,600 referenced issues.
- Unreferenced legacy placeholder arcs: 1,440.

No exact normalized title matches were found between legacy placeholder rows and canonical `FANDOM-EVENT-*` / `FANDOM-STORY-*` rows during the preflight query, so this cleanup is expected to be mostly renames, not merges.

## Compatibility

This is a data-only migration. Table shape and application queries remain compatible because `issues.story_arc_id` keeps referencing valid `story_arcs.id` values.

## Data Transformation

1. Back up `databases/spider-man.db`.
2. For each legacy story-arc row, compute a deterministic target ID.
3. Insert the target row if it does not already exist.
4. Update any `issues.story_arc_id` references from the old ID to the target ID.
5. Delete the old row after its data and references have moved.
6. Update the active Fandom volume importer so future placeholder arcs use `LOCAL-ARC-*`.

## Verification

Run:

```powershell
python scripts\db_normalize_story_arc_ids.py --db databases/spider-man.db --dry-run
python scripts\db_normalize_story_arc_ids.py --db databases/spider-man.db
python scripts\db_validate.py --db databases/spider-man.db
python -m py_compile scripts\db_normalize_story_arc_ids.py scripts\db_import_fandom_volume.py
```

Post-migration checks:

- No `story_arcs.id` values start with `ARC-`, `GCD-ARC-`, `MM-ARC-`, or `FANDOM-ARC-`.
- No issues reference missing story arcs.
- Reading-order export still returns all issue rows.

## Rollback

Restore the timestamped database backup made immediately before the cleanup.

## Classification

Data migration required, reversible by backup restore, requested by the user.

---

# Issue ID Cleanup

## Existing Design

Issue IDs still reflect the source or import era that created them:

- `ISS-*`
- `GCD-ISS-*`
- `MM-ISS-*`
- `FANDOM-ISS-*`

The simplified SQLite schema does not have child tables that reference `issues.id`; the organizer uses run, volume, issue number, release date, story arc, and `sort_order` for reading-order behavior.

## Proposed Design

Normalize all issue primary keys to a single deterministic Fandom-prefixed shape:

```text
FANDOM-ISS-<CAND-ID>-<ISSUE-NUMBER-SLUG>
```

Examples:

- `FANDOM-ISS-CAND-000002-14`
- `FANDOM-ISS-CAND-000034-27-NOW`

The active Fandom volume importer should use the same target ID for new issue rows.

## Requirement

The issue namespace should be consistent now that issue rows are sourced and repaired through Marvel Fandom workflows. Old `ISS-*`, `GCD-ISS-*`, and `MM-ISS-*` prefixes should not remain in the working database.

## Evidence

Current local counts before cleanup:

- `FANDOM-ISS-*`: 2,553 issues.
- `MM-ISS-*`: 1,236 issues.
- `GCD-ISS-*`: 10 issues.
- `ISS-*`: 4 issues.

A human-readable `run title + volume + issue` shape has collisions in the current data, while `cand_id + issue_number` has none because the schema already enforces `UNIQUE(cand_id, issue_number)`.

## Compatibility

This is a data-only primary-key rewrite. It is compatible with the simplified application path because no live database table references `issues.id`.

Any external notes, caches, or commands that refer to old issue IDs manually will need the new `FANDOM-ISS-<CAND-ID>-<ISSUE>` value.

## Data Transformation

1. Back up `databases/spider-man.db`.
2. Compute the target ID for every issue row.
3. Fail the migration if any target IDs collide.
4. Update `issues.id` in place.
5. Update the active Fandom volume importer to create the same ID shape.

## Verification

Run:

```powershell
python scripts\db_normalize_issue_ids.py --db databases/spider-man.db --dry-run
python scripts\db_normalize_issue_ids.py --db databases/spider-man.db
python scripts\db_validate.py --db databases/spider-man.db
python -m py_compile scripts\db_normalize_issue_ids.py scripts\db_import_fandom_volume.py
```

Post-migration checks:

- Every `issues.id` starts with `FANDOM-ISS-`.
- `COUNT(*)` from `issues` remains 3,803.
- `COUNT(DISTINCT id)` from `issues` remains 3,803.
- Reading-order loading still returns 3,803 entries.

## Rollback

Restore the timestamped database backup made immediately before the cleanup.

## Classification

Data migration required, reversible by backup restore, requested by the user.

