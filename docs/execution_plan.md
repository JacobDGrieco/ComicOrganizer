# Execution Plan

Research cutoff: 2026-07-30

The working goal is now a fast, useful Spider-Man download and reading-order index rather than an exhaustive publication encyclopedia.

SQLite is the working source of truth. JSON remains a compatibility/import/export format, not the format to manually rewrite for thousands of entries.

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

Supporting source, review, cover-date, event, and note fields may still be used when helpful, but they are no longer required for basic entry.

## Sorting Rule

Recommended reading order is derived as:

1. story arc start date
2. issue release date within that story arc
3. stable title/issue/id fallback when dates tie

This keeps multi-issue arcs together while still moving through publication history roughly year by year.

## Faster Workflow

1. Build series/run inventory from Marvel official pages first.
2. Add issue ranges from Marvel official series pages.
3. Assign each issue to a story arc.
4. Give each story arc a start date.
5. Run database validation.
6. Generate the reading list from SQLite.
7. Revisit only conflicts, crossovers, annuals, specials, and weird numbering in detail.

## Run-First Workflow

The current working pass is run inventory only. Do not import more issue rows until the download/research queue is useful enough for the user to prepare source downloads.

Seed and export the run queue:

```powershell
python scripts\db_init.py --db database/database.db
python scripts\db_seed_run_candidates.py --db database/database.db
python scripts\db_export_run_checklist.py --db database/database.db --priority P0
python scripts\db_export_run_checklist.py --db database/database.db --priority P1
```

Use priorities as:

- `P0`: core download set; start here.
- `P1`: strongly recommended Spider-family, alternate universe, event, or symbiote runs.
- `P2`: broader scope or lower-priority supporting material.

Run rows are not verified issue data. They exist so download preparation, source identification, and later issue imports can proceed in a controlled order.

## Marvel Official Workflow

Use Marvel as the primary source for run and issue discovery. Because Marvel blocks plain scripted HTTP for some pages, capture rendered pages first:

```powershell
npx --yes --package playwright node scripts\marvel_capture_page.js --url "https://www.marvel.com/comics/series" --output ".cache\marvel-series.html" --scroll
python scripts\marvel_scrape_series_index.py --input-html ".cache\marvel-series.html"
python scripts\marvel_scrape_series_index.py --input-html ".cache\marvel-series.html" --apply
python scripts\db_export_run_checklist.py --db database/database.db --priority P0
```

The scraper should be treated as official discovery. Reprints, facsimiles, collections, and variants are filtered out where obvious, but questionable rows still need manual scope review before issue import.

## Database Workflow

Initialize the database and import the current JSON data:

```powershell
python scripts\db_init.py --db database/database.db --reset
python scripts\db_import_json.py --db database/database.db
python scripts\db_validate.py --db database/database.db
```

Pull issue metadata from GCD for a known GCD series:

```powershell
python scripts\db_import_gcd_series.py --db database/database.db --gcd-series-id 1570 --run-id SER-000002 --dry-run --max-network-requests 10
python scripts\db_import_gcd_series.py --db database/database.db --gcd-series-id 1570 --run-id SER-000002 --max-network-requests 10
python scripts\db_validate.py --db database/database.db
```

Use `--dry-run` first. The importer skips GCD records marked as variants by default and imports one row per issue number. Run it repeatedly in small batches so GCD rate limits do not wipe out progress.

For fallback bulk issue-list imports, use the Marvel Metadata API importer:

```powershell
python scripts\db_search_marvel_metadata_series.py "The Amazing Spider-Man (1963"
python scripts\db_import_marvel_metadata_series.py --db database/database.db --marvel-series-id 1987 --run-id SER-000002 --dry-run
python scripts\db_import_marvel_metadata_series.py --db database/database.db --marvel-series-id 1987 --run-id SER-000002
python scripts\db_validate.py --db database/database.db
```

This source is unofficial, but it is designed for reading-list metadata, supports series issue lists, and has a documented 60 requests/minute limit. Use it for speed, then use GCD/Marvel/manual checks for conflicts, special cases, and story arc cleanup.

If the Marvel Metadata issue count is incomplete, switch that run to a local GCD SQLite dump import:

```powershell
python scripts\db_import_gcd_sqlite_series.py --db database/database.db --gcd-db "D:\Path\To\gcd.sqlite3" --gcd-series-id 3059 --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --dry-run
python scripts\db_import_gcd_sqlite_series.py --db database/database.db --gcd-db "D:\Path\To\gcd.sqlite3" --gcd-series-id 3059 --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1
python scripts\db_validate.py --db database/database.db
```

Use this fallback for Web of Spider-Man (1985 series) and Web of Spider-Man Annual unless a faster complete source is found. The importer reads the dump locally, so it avoids the GCD per-issue API rate limit while still preserving GCD issue URLs as sources.

For smaller repairs, use the GCD series details export importer before downloading the full dump:

```powershell
python scripts\db_import_gcd_details_export.py --db database/database.db --gcd-series-id 3059 --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --expected-count 129 --dry-run
```

If GCD blocks the scripted export request, download the details page `.csv` or `.json` export in a browser and rerun with `--input`. This is still preferred over HTML scraping because the table export is structured and less likely to break if the site layout changes.

Export the organizer-compatible order when needed:

```powershell
python scripts\db_export_reading_order.py --db database/database.db
```

Point `config.json` at the SQLite database:

```json
{
	"reading_order_path": "database/database.db"
}
```

## Research Packet Helper

The packet helper still exists for quick JSON skeletons during manual research:

```powershell
node scripts/researchPacket.js --series SER-000002 --count 25
```

The packet prints:

- search links for Marvel, GCD, and story arc/order checks
- issue JSON skeletons
- story arc JSON skeletons

It does not verify or write data. For the SQL workflow, treat the packet as a prompt/checklist and insert researched facts into SQLite.

## Validation

Run the legacy JSON validator:

```powershell
node scripts/validate.js
```

Run the SQLite validator:

```powershell
python scripts\db_validate.py --db database/database.db
```

## Reading List Output

Legacy JSON output:

```powershell
node scripts/buildReadingOrder.js
```

SQLite output:

```powershell
python scripts\db_export_reading_order.py --db database/database.db
```

The output includes the minimal fields needed for download and reading.
