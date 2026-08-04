# Execution Plan

Research cutoff: 2026-07-30

The working goal is a fast, useful Spider-Man download and reading-order index rather than an exhaustive publication encyclopedia.

SQLite is the working source of truth. Reading-order data lives in `databases/<project>.db`; for Spider-Man, use `databases/spider-man.db`.

## Minimal Data Contract

Each completed issue needs only:

- comic run
- issue number
- issue release date
- comic run start date
- comic run end date
- universe
- main character or characters
- story arc

Supporting source, review, cover-date, event, and note fields may still be used when helpful, but they are no longer required for basic organizer output.

## Sorting Rule

Recommended reading order is derived as:

1. story arc start date
2. issue release date within that story arc
3. stable title/issue/id fallback when dates tie

This keeps multi-issue arcs together while still moving through publication history roughly year by year.

## Faster Workflow

1. Build series/run inventory from Marvel official pages first.
2. Add issue ranges from reliable database-backed import or manual entry workflows.
3. Assign each issue to a story arc.
4. Give each story arc a start date.
5. Run database validation.
6. Read the organizer list directly from SQLite.
7. Revisit only conflicts, crossovers, annuals, specials, and unusual numbering in detail.

## Project Wiring

Project commands infer the root SQLite database from `projects/<group>/config.json`:

```json
{
	"character_list_path": "characters.md"
}
```

Keep additional project databases in the same root folder:

```text
databases/
  spider-man.db
  x-men.db
```

## Validation

Run the organizer-facing list command to verify that the configured database can be read:

```powershell
python -m sorting.list_order --config projects/spider-man/config.json
```

Run the full code checks:

```powershell
npm run check
```
