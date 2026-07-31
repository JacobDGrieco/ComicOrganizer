# Comic Organizer

Python utilities for organizing Tachidesk/Suwayomi comic downloads into a single reading-order folder.

The main organizer reads a SQLite reading-order database or legacy JSON sort-order file, matches downloaded `.cbz` files by run, volume, and issue, then renames/moves them into:

```text
NNNN - <Output Name> #<Issue>.cbz
```

Example:

```text
0455 - The Amazing Spider-Man #396.cbz
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
```

Run for real:

```powershell
python -m sorting.organizer --config config.json
```

The organizer is safe to rerun. It checks existing destination files by their `NNNN - ` prefix and skips reading-order positions that are already present.

## Config

`config.json` controls all paths and naming.

For the Spider-Man project, point `reading_order_path` at the SQLite database:

```json
{
	"reading_order_path": "database.db"
}
```

The organizer reads SQLite rows in this order:

```text
story arc start date -> issue release date -> stable title/issue fallback
```

This keeps a story arc together while still moving through publication history.

## SQLite Database

Initialize and import the current JSON research data:

```powershell
python scripts\db_init.py --db database.db --reset
python scripts\db_seed_run_candidates.py --db database.db
python scripts\db_validate.py --db database.db
```

The simplified working schema keeps only:

- `comic_runs`
- `issues`
- `story_arcs`

Existing older databases can be migrated with:

```powershell
python scripts\db_migrate_simplify_schema.py --db database.db --dry-run
python scripts\db_migrate_simplify_schema.py --db database.db
```

Import issue metadata from GCD for a known series:

```powershell
python scripts\db_import_gcd_series.py --db database.db --gcd-series-id 1570 --run-id SER-000002 --dry-run --max-network-requests 10
python scripts\db_import_gcd_series.py --db database.db --gcd-series-id 1570 --run-id SER-000002 --max-network-requests 10
python scripts\db_validate.py --db database.db
```

The GCD importer uses GCD issue `on_sale_date` when available, skips records marked as variants unless `--include-variants` is passed, and creates temporary per-issue story arcs until proper arc grouping is researched. Run it repeatedly in small batches; cached responses and already imported issue numbers are skipped.

For faster Marvel issue-list imports, use the Marvel Metadata API importer:

```powershell
python scripts\db_search_marvel_metadata_series.py "The Amazing Spider-Man (1963"
python scripts\db_import_marvel_metadata_series.py --db database.db --marvel-series-id 1987 --run-id SER-000002 --dry-run
python scripts\db_import_marvel_metadata_series.py --db database.db --marvel-series-id 1987 --run-id SER-000002
python scripts\db_validate.py --db database.db
```

This source can import large series in a few paginated requests. Existing issue dates are preserved unless `--refresh-existing` is passed.

Some Marvel Metadata series are incomplete. For example, Web of Spider-Man (1985 - 1995) is listed there with fewer issues than Marvel's public page and GCD. For those cases, use a local GCD SQLite dump instead of the rate-limited GCD API:

```powershell
python scripts\db_import_gcd_sqlite_series.py --db database.db --gcd-db "D:\Path\To\gcd.sqlite3" --gcd-series-id 3059 --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --dry-run
python scripts\db_import_gcd_sqlite_series.py --db database.db --gcd-db "D:\Path\To\gcd.sqlite3" --gcd-series-id 3059 --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1
python scripts\db_validate.py --db database.db
```

The local GCD importer avoids web rate limits because it reads from the downloaded dump. It imports one reading entry per issue number by default, collapses direct/newsstand/variant rows, prefers exact `on_sale_date` values, and stores source URLs back to the selected GCD issue records. Use `--include-variants` only if you explicitly want variants as separate reading entries.

If you do not want to download the full GCD SQLite dump, use GCD's series details export as the smaller fallback. The script tries the public JSON export URL by default, but GCD may block scripted requests. If that happens, open the series details page in a browser, click the `.csv` or `.json` export link, save it locally, and pass it with `--input`:

```powershell
python scripts\db_import_gcd_details_export.py --db database.db --gcd-series-id 3059 --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --expected-count 129 --dry-run
python scripts\db_import_gcd_details_export.py --db database.db --gcd-series-id 3059 --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --expected-count 129

python scripts\db_import_gcd_details_export.py --db database.db --gcd-series-id 3059 --input "D:\Downloads\web-of-spider-man-gcd.csv" --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --expected-count 129 --dry-run
python scripts\db_import_gcd_details_export.py --db database.db --gcd-series-id 3059 --input "D:\Downloads\web-of-spider-man-gcd.csv" --run-id SER-000018 --run-title "Web of Spider-Man" --volume 1 --expected-count 129
python scripts\db_validate.py --db database.db
```

Use `--expected-count` on gap-repair imports. It makes the import fail loudly when the source does not contain the issue count we expect.

Export a compact JSON reading order when needed:

```powershell
python scripts\db_export_reading_order.py --db database.db
```

The database schema is in `database/schema.sql`.

## Run Checklist

Before importing issue rows, maintain the run-level download/research queue:

```powershell
python scripts\db_seed_run_candidates.py --db database.db
python scripts\db_export_run_checklist.py --db database.db --priority P0
python scripts\db_export_run_checklist.py --db database.db --priority P0 --format csv
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

The array order is the destination position order. The first entry becomes `0001`, the second becomes `0002`, and so on.

Source folder example:

```json
{
	"path": "C:\\Users\\gamin\\AppData\\Local\\Tachidesk\\downloads\\mangas\\ReadAllComics (EN)\\Amazing Spider-Man (Publisher_ Marvel)",
	"run": "The Amazing Spider-Man",
	"output_name": "The Amazing Spider-Man",
	"volume": 1,
	"annual_run": "Amazing Spider-Man Annual",
	"annual_output_name": "The Amazing Spider-Man Annual",
	"annual_volume": 1
}
```

Fields:

- `path`: folder containing downloaded `.cbz` files.
- `run`: exact reading-order `run` value used for matching.
- `output_name`: name used in moved filenames. Defaults to `run`.
- `volume`: default reading-order `volume` for files in this folder. Defaults to `1`.
- `annual_run`: reading-order `run` value for annual files in this folder. Defaults to `<run> Annual`.
- `annual_output_name`: output name for annual files. Defaults to `<output_name> Annual`.
- `annual_volume`: default reading-order `volume` for annual files. Defaults to `volume`.

Filename `vN` volume markers override config volume for that file. For example, `v2 001.cbz` matches reading-order volume `2` even if the folder config says `"volume": 1`.

Source folders do not need to exist yet. Missing or unreachable source folders are reported as warnings and skipped, so you can add paths to `config.json` before those series finish downloading.

Supported filename formats include:

```text
Issue #12.cbz
Issue 12.cbz
v1 141.cbz
v1 .Annual 010.cbz
Annual 10.cbz
Annual_1.cbz
Annual_#12.cbz
Annual 42 (2018).cbz
94_-_Who_Was_Joey_Z.cbz
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

## Position Shifter

Use `python -m sorting.shift_positions` when you need to insert a missing issue into the destination folder and shift existing `NNNN - ` prefixes out of the way.

Dry run:

```powershell
python -m sorting.shift_positions "0004 - The Amazing Spider-Man #3.cbz" --folder "D:\Suwayomi\Comics\Spider-Verse"
```

Dry run using `config.json` for the destination folder:

```powershell
python -m sorting.shift_positions "0004 - The Amazing Spider-Man #3.cbz" --config config.json
```

Apply:

```powershell
python -m sorting.shift_positions "0004 - The Amazing Spider-Man #3.cbz" --folder "D:\Suwayomi\Comics\Spider-Verse" --apply
```

Custom increment:

```powershell
python -m sorting.shift_positions "0004 - The Amazing Spider-Man #3.cbz" --folder "D:\Suwayomi\Comics\Spider-Verse" --increment 2 --apply
```

The selected file and every prefixed file after it are shifted. With the default increment of `1`, this means:

```text
0004 - The Amazing Spider-Man #3.cbz -> 0005 - The Amazing Spider-Man #3.cbz
0005 - ... -> 0006 - ...
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

The old-reading-order mode is safest because it uses each existing file's current `NNNN` prefix to find the old JSON entry, then matches that issue in the new JSON file by `Run + Volume + Issue`. This avoids mistakes when a run has multiple volumes with repeated issue numbers.

Fallback dry run without an old JSON reference:

```powershell
python -m sorting.migrate_sort_order --config config.json
```

Fallback mode decodes names like `0455 - The Amazing Spider-Man #396.cbz` and looks for the same title/issue in the new JSON file. If that title/issue appears in multiple volumes, the tool warns and skips that file until you provide `--old-reading-order`.

Migration applies renames through temporary filenames first, so swaps such as `0001 <-> 0002` are handled without overwriting.

## Tests

Run all tests:

```powershell
python -m unittest discover -s tests
```
