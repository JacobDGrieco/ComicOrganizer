# Comic Organizer

Python utilities for organizing Tachidesk/Suwayomi comic downloads into a single reading-order folder.

The organizer uses SQLite as the reading-order source of truth. Reading-order databases live in the root `databases/` folder and are named for the project or group, for example:

```text
databases/
  schema.sql
  spider-man.db
```

The Spider-Man project config lives at `projects/spider-man/config.json`, so project commands infer `databases/spider-man.db`.

## Setup

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Organizer

Run a dry run first:

```powershell
python -m sorting.organizer --config projects/spider-man/config.json --dry-run
npm run sort:dry -- spider-man
```

Run for real:

```powershell
python -m sorting.organizer --config projects/spider-man/config.json
npm run sort -- spider-man
```

The organizer is safe to rerun. It checks existing destination files by their numeric prefix and skips reading-order positions that are already present.

To report gaps in the output folder:

```powershell
python -m sorting.missing_entries --config projects/spider-man/config.json
npm run missing -- spider-man
```

To print the current database reading order:

```powershell
python -m sorting.list_order --config projects/spider-man/config.json
npm run list -- spider-man
```

Useful npm shortcuts:

```powershell
npm run sort:dry -- spider-man
npm run sort -- spider-man
npm run missing -- spider-man
npm run list -- spider-man
npm run reindex:dry -- spider-man
npm run reindex -- spider-man
npm run download
npm run download:headless
npm run flatten:dry -- spider-man
npm run flatten -- spider-man
npm run check
```

## Project Configs

A project `config.json` controls the SQLite database, destination folder, scan folders, and optional log paths. Config files stay under `projects/<name>/`, while reading-order databases stay under root `databases/`.

```text
projects/
  spider-man/
    config.json
    characters.md
    downloader/
      urls.csv
      downloads/
    logs/
  x-men/
    config.json
    characters.md
    downloader/
      urls.csv
      downloads/
    logs/

databases/
  spider-man.db
  x-men.db
```

Example project config:

```json
{
	"project_name": "Spider-Man",
	"character_list_path": "characters.md",
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

When `reading_order_path` is omitted from `projects/<group>/config.json`, commands use `databases/<group>.db`. Relative paths that remain in the config, such as `characters.md`, are resolved next to the config file.

## Reading Order

The organizer reads SQLite rows in this order:

```text
story arc start date -> issue release date -> issue sort_order when present -> stable title/issue fallback
```

For ongoing runs released in 2024 or later, the first two keys are flipped so newer crossover tags do not pull a later issue ahead of earlier issues from the same modern run:

```text
issue release date -> story arc start date -> issue sort_order when present -> stable title/issue fallback
```

The database schema is in `databases/schema.sql`.

## Source Folders

Fields:

- `path`: folder containing downloaded `.cbz` files.
- `run`: exact `comic_runs.title` value used for regular issue matching.
- `volume`: exact `comic_runs.volume` value used for regular issue matching.
- `annual_run`: database `comic_runs.title` value for annual files in this folder. Defaults to `<run> Annual`.
- `annual_volume`: exact `comic_runs.volume` value for annual files in this folder. Defaults to `volume`.
- `annual_start_year`: optional annual database run start year, used only when the same annual title has repeated issue numbers across multiple database runs.
- `special_run`: database `comic_runs.title` value for special files in this folder. Defaults to `<run> Special`.
- `special_volume`: exact `comic_runs.volume` value for special files in this folder. Defaults to `volume`.
- `issue_aliases`: optional map from normalized filename issue labels to database issue labels.
- `source_title_aliases`: optional source filename titles that should match the configured database run.

Moved files keep the original normalized filename after the five-digit reading-order prefix:

```text
00455 - The Amazing Spider-Man 1963 #396.cbz
```

Source folders do not need to exist yet. Missing or unreachable source folders are reported as warnings and skipped.

## Reindexing

Use `sorting.reindex_output` after fixing database dates, story arcs, or sort order and you need existing destination filenames renumbered to match the current database order.

Dry run:

```powershell
python -m sorting.reindex_output --config projects/spider-man/config.json
npm run reindex:dry -- spider-man
```

Apply:

```powershell
python -m sorting.reindex_output --config projects/spider-man/config.json --apply
npm run reindex -- spider-man
```

The script scans `destination_folder`, strips the leading `##### - ` prefix, parses the original normalized filename, matches it against the configured database reading order, and renames only the numeric prefix.

## Position Shifter

Use `sorting.shift_positions` when you need to insert a missing issue into the destination folder and shift existing numeric prefixes out of the way.

Dry run:

```powershell
python -m sorting.shift_positions "00004 - The Amazing Spider-Man 1963 #3.cbz" --config projects/spider-man/config.json
```

Apply:

```powershell
python -m sorting.shift_positions "00004 - The Amazing Spider-Man 1963 #3.cbz" --config projects/spider-man/config.json --apply
```

After shifting destination files, add or adjust the matching issue row in the project database.

## Tests

Run all checks:

```powershell
npm run check
```
