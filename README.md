# Comic Organizer

Python utilities for organizing Tachidesk/Suwayomi comic downloads into a single reading-order folder.

The main organizer reads the SQLite reading-order database, matches normalized downloaded `.cbz` filenames to database issues, then renames/moves them into:

```text
##### - <Original Filename>.cbz
```

Example:

```text
00455 - The Amazing Spider-Man 1963 #396.cbz
```

## Setup

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Organizer

Run a dry run first:

```powershell
python -m sorting.organizer --config config.json --dry-run
npm run sort:dry
```

Run for real:

```powershell
python -m sorting.organizer --config config.json
npm run sort
```

The organizer is safe to rerun. It checks existing destination files by their numeric prefix and skips reading-order positions that are already present.

To report gaps in the output folder, run:

```powershell
python -m sorting.missing_entries --config config.json
npm run missing
```

The report finds the highest existing numeric prefix in the destination folder, lists every comic run with at least one missing issue in that range, then lists every missing database reading-order entry from position `00001` through that last existing position. It prints to the terminal and writes the same lines to `logs/missing-entries.log` next to the config file by default. Use `--output path\to\missing.log` to choose a different log file.

To print the current reading-order list, run:

```powershell
python -m sorting.list_order --config config.json
npm run list
```

The report prints two sections: the first appearance of each comic run by numeric position, then every issue in full sort order. It also writes the same lines to `logs/reading-order-list.log` next to the config file by default.

The downloader and CBZ flattener also mirror terminal output to logs by default:

```powershell
npm run download
npm run flatten
```

Downloader output is written to `logs/downloader.log`. CBZ flattening output is written to `logs/flatten-cbz.log`.

Useful npm shortcuts:

```powershell
npm run sort:dry
npm run sort
npm run missing
npm run list
npm run download
npm run flatten
npm run reindex
npm run db:validate
npm run db:export
npm test
npm run check
```

## Config

`config.json` controls the SQLite database, destination folder, scan folders, and optional organizer log path. When `log_path` is omitted, organizer output is written to `logs/comic-organizer.log` next to the config file.

For the Spider-Man project, point `reading_order_path` at the SQLite database:

```json
{
	"reading_order_path": "database/database.db",
	"destination_folder": "D:\\Suwayomi\\Comics\\Spider-Man Reading Order",
	"source_folders": [
		{
			"path": "D:\\Suwayomi\\Downloads\\Amazing Spider-Man",
			"run": "The Amazing Spider-Man",
			"volume": 1,
			"annual_run": "Amazing Spider-Man Annual",
			"annual_volume": 1
		}
	]
}
```

The organizer reads SQLite rows in this order:

```text
story arc start date -> issue release date -> issue sort_order when present -> stable title/issue fallback
```

This keeps a story arc together while still moving through publication history.

For ongoing runs released in 2024 or later, the first two keys are flipped so newer crossover tags do not pull a later issue ahead of earlier issues from the same modern run:

```text
issue release date -> story arc start date -> issue sort_order when present -> stable title/issue fallback
```

The terminal output and organizer log start with unmatched scanned files, then show the planned or applied conversions in this shape:

```text
Unmatched scanned files:
  SourceFolder\The Amazing Spider-Man 1963 #999.cbz

Conversions:
  SourceFolder\The Amazing Spider-Man 1963 #396.cbz -> 00455 - The Amazing Spider-Man 1963 #396.cbz
```

## SQLite Database

Initialize and import the current JSON research data:

```powershell
python scripts\db_init.py --db database/database.db --reset
python scripts\db_seed_run_candidates.py --db database/database.db
python scripts\db_validate.py --db database/database.db
```

The simplified working schema keeps only:

- `comic_runs`
- `issues`
- `story_arcs`

Story-arc IDs use these namespaces:

- `FANDOM-EVENT-*` for event groupings found on Marvel Fandom.
- `FANDOM-STORY-*` for story-arc groupings found on Marvel Fandom.
- `LOCAL-ARC-*` for local fallback placeholders.

Issue IDs use `FANDOM-ISS-<comic_runs.id>-<issue-number>`, such as `FANDOM-ISS-CAND-000002-14`.

Existing older databases can be migrated with:

```powershell
python scripts\db_migrate_simplify_schema.py --db database/database.db --dry-run
python scripts\db_migrate_simplify_schema.py --db database/database.db
```

Import issue metadata from GCD for a known series:

```powershell
python scripts\db_import_gcd_series.py --db database/database.db --gcd-series-id 1570 --run-id SER-000002 --dry-run --max-network-requests 10
python scripts\db_import_gcd_series.py --db database/database.db --gcd-series-id 1570 --run-id SER-000002 --max-network-requests 10
python scripts\db_validate.py --db database/database.db
```

The GCD importer uses GCD issue `on_sale_date` when available, skips records marked as variants unless `--include-variants` is passed, and creates temporary per-issue story arcs until proper arc grouping is researched. Run it repeatedly in small batches; cached responses and already imported issue numbers are skipped.

For faster Marvel issue-list imports, use the Marvel Metadata API importer:

```powershell
python scripts\db_search_marvel_metadata_series.py "The Amazing Spider-Man (1963"
python scripts\db_import_marvel_metadata_series.py --db database/database.db --marvel-series-id 1987 --run-id SER-000002 --dry-run
python scripts\db_import_marvel_metadata_series.py --db database/database.db --marvel-series-id 1987 --run-id SER-000002
python scripts\db_validate.py --db database/database.db
```

This source can import large series in a few paginated requests. Existing issue dates are preserved unless `--refresh-existing` is passed.

Some Marvel Metadata series are incomplete. For example, Web of Spider-Man (1985 - 1995) is listed there with fewer issues than Marvel's public page and GCD. For those cases, use a local GCD SQLite dump instead of the rate-limited GCD API:

```powershell
python scripts\db_import_gcd_sqlite_series.py --db database/database.db --gcd-db "D:\Path\To\gcd.sqlite3" --gcd-series-id 3059 --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --dry-run
python scripts\db_import_gcd_sqlite_series.py --db database/database.db --gcd-db "D:\Path\To\gcd.sqlite3" --gcd-series-id 3059 --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1
python scripts\db_validate.py --db database/database.db
```

The local GCD importer avoids web rate limits because it reads from the downloaded dump. It imports one reading entry per issue number by default, collapses direct/newsstand/variant rows, prefers exact `on_sale_date` values, and stores source URLs back to the selected GCD issue records. Use `--include-variants` only if you explicitly want variants as separate reading entries.

If you do not want to download the full GCD SQLite dump, use GCD's series details export as the smaller fallback. The script tries the public JSON export URL by default, but GCD may block scripted requests. If that happens, open the series details page in a browser, click the `.csv` or `.json` export link, save it locally, and pass it with `--input`:

```powershell
python scripts\db_import_gcd_details_export.py --db database/database.db --gcd-series-id 3059 --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --expected-count 129 --dry-run
python scripts\db_import_gcd_details_export.py --db database/database.db --gcd-series-id 3059 --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --expected-count 129

python scripts\db_import_gcd_details_export.py --db database/database.db --gcd-series-id 3059 --input "D:\Downloads\web-of-spider-man-gcd.csv" --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --expected-count 129 --dry-run
python scripts\db_import_gcd_details_export.py --db database/database.db --gcd-series-id 3059 --input "D:\Downloads\web-of-spider-man-gcd.csv" --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --expected-count 129
python scripts\db_validate.py --db database/database.db
```

Use `--expected-count` on gap-repair imports. It makes the import fail loudly when the source does not contain the issue count we expect.

Export a compact JSON reading order when needed:

```powershell
python scripts\db_export_reading_order.py --db database/database.db
```

The database schema is in `database/schema.sql`.

## Run Checklist

Before importing issue rows, maintain the run-level download/research queue:

```powershell
python scripts\db_seed_run_candidates.py --db database/database.db
python scripts\db_export_run_checklist.py --db database/database.db --priority P0
python scripts\db_export_run_checklist.py --db database/database.db --priority P0 --format csv
```

The checklist is intentionally run-level only. It does not claim that issue rows, annual counts, or story arcs are complete.

## Marvel Official Scrape

Marvel blocks plain scripted HTTP for some public pages. Capture the rendered page with Playwright, then parse the saved HTML:

```powershell
npx --yes --package playwright node scripts\marvel_capture_page.js --url "https://www.marvel.com/comics/series" --output ".cache\marvel-series.html" --scroll
python scripts\marvel_scrape_series_index.py --input-html ".cache\marvel-series.html"
python scripts\marvel_scrape_series_index.py --input-html ".cache\marvel-series.html" --apply
```

The scraper excludes obvious reprints, collections, facsimiles, variants, and similar non-original-publication rows. Treat its output as official Marvel discovery data that still needs scope review before issue import.

## Marvel Fandom Issue Imports

When Marvel's official series page is recorded on a run but the issue rows are still missing, import the dated Marvel Fandom volume list into the simplified SQLite schema:

```powershell
python scripts\db_import_fandom_volume.py --db database/database.db --run-id CAND-000022 --fandom-page Spider-Man_Vol_1 --dry-run
python scripts\db_import_fandom_volume.py --db database/database.db --run-id CAND-000022 --fandom-page Spider-Man_Vol_1 --max-release-date 2026-07-31
python scripts\db_validate.py --db database/database.db
```

The importer creates one issue row per dated issue and links it to the existing `comic_runs.id`. It creates placeholder story-arc rows because the current schema requires `issues.story_arc_id`; those rows should be replaced or regrouped during a later story-arc pass. Use `--max-release-date` for ongoing runs so future solicited issues are not imported before release.

For one-shots or graphic novels where Fandom has a single issue page instead of a volume issue list, pass that issue page with `--issue-number 1`.

## Marvel Fandom Story-Arc Backfill

After issue rows exist, backfill Fandom event/story-arc assignments and within-arc order:

```powershell
python scripts\db_backfill_fandom_story_arcs.py --db database/database.db --dry-run --limit 25
python scripts\db_backfill_fandom_story_arcs.py --db database/database.db --limit 300 --offset 0
python scripts\db_validate.py --db database/database.db
```

The backfill reads issue-page `EventN` fields first, then `StoryArcN` fields. If multiple candidates are present, it chooses the event/story-arc page with the earliest detected start date. It fills `issues.sort_order` when Fandom exposes a `Reading Order:` list or ordered `PartN` fields; otherwise the organizer falls back to release date inside the selected arc.

## Legacy JSON Sort Order

Reading-order JSON files are still supported. They are ordered arrays, either as a bare array or inside an `entries` property:

```json
{
	"entries": [
		{ "run": "Amazing Fantasy", "volume": 1, "issue": "15" },
		{ "run": "The Amazing Spider-Man", "volume": 1, "issue": "1" }
	]
}
```

The array order is the destination position order. The first entry becomes `00001`, the second becomes `00002`, and so on.

Source folder example:

```json
{
	"path": "C:\\Users\\gamin\\AppData\\Local\\Tachidesk\\downloads\\mangas\\ReadAllComics (EN)\\Amazing Spider-Man (Publisher_ Marvel)",
	"run": "The Amazing Spider-Man",
	"volume": 1,
	"annual_run": "Amazing Spider-Man Annual",
	"annual_volume": 1,
	"issue_aliases": {
		"16.HU": "16.1"
	}
}
```

Fields:

- `path`: folder containing downloaded `.cbz` files.
- `run`: exact `comic_runs.title` value used for regular issue matching.
- `volume`: exact `comic_runs.volume` value used for regular issue matching.
- `annual_run`: reading-order `run` value for annual files in this folder. Defaults to `<run> Annual`.
- `annual_volume`: exact `comic_runs.volume` value for annual files in this folder. Defaults to `volume`.
- `annual_start_year`: optional annual database run start year, used only when the same annual title has repeated issue numbers across multiple database runs.
- `issue_aliases`: optional map from normalized filename issue labels to database issue labels, useful when source files use arc suffixes like `16.HU` while Fandom stores the same issue as `16.1`.

Moved files keep the original normalized filename after the five-digit reading-order prefix.

Source folders do not need to exist yet. Missing or unreachable source folders are reported as warnings and skipped, so you can add paths to `config.json` before those series finish downloading.

Supported filename formats include:

```text
<comic run name> <comic run start year> #<issue number>.cbz
<comic run name> (<comic run start year>) #<issue number>.cbz
<comic run name> <comic run start year> Annual #<issue number>.cbz
<comic run name> (<comic run start year>) Annual #<issue number>.cbz
<comic run name> <comic run start year> Annual 'YY.cbz
<comic run name> (<comic run start year>) Annual 'YY.cbz
```

Examples:

```text
The Amazing Spider-Man 1963 #396.cbz
The Amazing Spider-Man (1963) #396.cbz
The Amazing Spider-Man 1963 #-1.cbz
The Amazing Spider-Man 1963 #27.NOW.cbz
The Amazing Spider-Man 1963 Annual #28.cbz
The Amazing Spider-Man 1963 Annual '94.cbz
```

## Issue Overrides

Use `issue_overrides` when the generated/source sort-order issue label differs from the real/source issue number.

Example:

```json
"issue_overrides": {
	"Amazing Fantasy": {
		"1": "15"
	}
}
```

This keeps the sort-order JSON unchanged while matching/outputting `Amazing Fantasy #15`.

## Output Reindex

Use `python -m sorting.reindex_output` after fixing database dates, story arcs, or sort order and you need existing destination filenames renumbered to match the current database order.

Dry run:

```powershell
python -m sorting.reindex_output --config config.json
npm run reindex
```

Apply:

```powershell
python -m sorting.reindex_output --config config.json --apply
```

The script scans `destination_folder`, strips the leading `##### - ` prefix, parses the original normalized filename, matches it against the current configured reading order, and renames only the numeric prefix. It writes the same terminal output to `logs/reindex-output.log` next to the config file.

## Position Shifter

Use `python -m sorting.shift_positions` when you need to insert a missing issue into the destination folder and shift existing numeric prefixes out of the way.

Dry run:

```powershell
python -m sorting.shift_positions "00004 - The Amazing Spider-Man 1963 #3.cbz" --folder "D:\Suwayomi\Comics\Spider-Verse"
```

Dry run using `config.json` for the destination folder:

```powershell
python -m sorting.shift_positions "00004 - The Amazing Spider-Man 1963 #3.cbz" --config config.json
```

Apply:

```powershell
python -m sorting.shift_positions "00004 - The Amazing Spider-Man 1963 #3.cbz" --folder "D:\Suwayomi\Comics\Spider-Verse" --apply
```

Custom increment:

```powershell
python -m sorting.shift_positions "00004 - The Amazing Spider-Man 1963 #3.cbz" --folder "D:\Suwayomi\Comics\Spider-Verse" --increment 2 --apply
```

The selected file and every prefixed file after it are shifted. With the default increment of `1`, this means:

```text
00004 - The Amazing Spider-Man 1963 #3.cbz -> 00005 - The Amazing Spider-Man 1963 #3.cbz
00005 - ... -> 00006 - ...
```

The shifter validates target position collisions before renaming anything. Without `--apply`, it only prints the plan.

After shifting destination files, insert the new issue entry directly into the JSON sort-order file at the matching array position.

## Sort-Order Migration

Use `python -m sorting.migrate_sort_order` when you rebuild the JSON sort order and need existing destination files renumbered to match the new entry positions.

Recommended dry run using the old JSON file as a reference:

```powershell
python -m sorting.migrate_sort_order --config config.json --old-reading-order "sort_orders\spider-verse-old.json"
```

Apply:

```powershell
python -m sorting.migrate_sort_order --config config.json --old-reading-order "sort_orders\spider-verse-old.json" --apply
```

With `--config`, the tool uses:

- `destination_folder` as the folder to rename.
- `reading_order_path` as the new/reworked SQLite database or JSON sort order.
- Config output names as aliases when decoding filenames.

The old-reading-order mode is safest because it uses each existing file's current numeric prefix to find the old JSON entry, then matches that issue in the new JSON file by `Run + Volume + Issue`. This avoids mistakes when a run has multiple volumes with repeated issue numbers.

Fallback dry run without an old JSON reference:

```powershell
python -m sorting.migrate_sort_order --config config.json
```

Fallback mode decodes legacy generated names like `00455 - The Amazing Spider-Man #396.cbz` and looks for the same title/issue in the new JSON file. If that title/issue appears in multiple volumes, the tool warns and skips that file until you provide `--old-reading-order`.

Migration applies renames through temporary filenames first, so swaps such as `0001 <-> 0002` are handled without overwriting.

## Tests

Run all tests:

```powershell
python -m unittest discover -s tests
```
