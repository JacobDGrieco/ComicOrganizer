# Comic Organizer

Python utilities for organizing Tachidesk/Suwayomi comic downloads into a single reading-order folder.

The main organizer reads a JSON sort-order file, matches downloaded `.cbz` files by run, volume, and issue, then renames/moves them into:

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
python organizer.py --config config.json --dry-run
```

Run for real:

```powershell
python organizer.py --config config.json
```

The organizer is safe to rerun. It checks existing destination files by their `NNNN - ` prefix and skips reading-order positions that are already present.

## Config

`config.json` controls all paths and naming.

Reading-order files are ordered JSON arrays, either as a bare array or inside an `entries` property:

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

Use `shift_positions.py` when you need to insert a missing issue into the destination folder and shift existing `NNNN - ` prefixes out of the way.

Dry run:

```powershell
python shift_positions.py "0004 - The Amazing Spider-Man #3.cbz" --folder "D:\Suwayomi\Comics\Spider-Verse"
```

Dry run using `config.json` for the destination folder:

```powershell
python shift_positions.py "0004 - The Amazing Spider-Man #3.cbz" --config config.json
```

Apply:

```powershell
python shift_positions.py "0004 - The Amazing Spider-Man #3.cbz" --folder "D:\Suwayomi\Comics\Spider-Verse" --apply
```

Custom increment:

```powershell
python shift_positions.py "0004 - The Amazing Spider-Man #3.cbz" --folder "D:\Suwayomi\Comics\Spider-Verse" --increment 2 --apply
```

The selected file and every prefixed file after it are shifted. With the default increment of `1`, this means:

```text
0004 - The Amazing Spider-Man #3.cbz -> 0005 - The Amazing Spider-Man #3.cbz
0005 - ... -> 0006 - ...
```

The shifter validates target position collisions before renaming anything. Without `--apply`, it only prints the plan.

After shifting destination files, insert the new issue entry directly into the JSON sort-order file at the matching array position.

## Sort-Order Migration

Use `migrate_sort_order.py` when you rebuild the JSON sort order and need existing destination files renumbered to match the new entry positions.

Recommended dry run using the old JSON file as a reference:

```powershell
python migrate_sort_order.py --config config.json --old-reading-order "sort_orders\spider-verse-old.json"
```

Apply:

```powershell
python migrate_sort_order.py --config config.json --old-reading-order "sort_orders\spider-verse-old.json" --apply
```

With `--config`, the tool uses:

- `destination_folder` as the folder to rename.
- `reading_order_path` as the new/reworked JSON sort order.
- Config output names as aliases when decoding filenames.

The old-reading-order mode is safest because it uses each existing file's current `NNNN` prefix to find the old JSON entry, then matches that issue in the new JSON file by `Run + Volume + Issue`. This avoids mistakes when a run has multiple volumes with repeated issue numbers.

Fallback dry run without an old JSON reference:

```powershell
python migrate_sort_order.py --config config.json
```

Fallback mode decodes names like `0455 - The Amazing Spider-Man #396.cbz` and looks for the same title/issue in the new JSON file. If that title/issue appears in multiple volumes, the tool warns and skips that file until you provide `--old-reading-order`.

Migration applies renames through temporary filenames first, so swaps such as `0001 <-> 0002` are handled without overwriting.

## Tests

Run all tests:

```powershell
python -m unittest discover -s tests
```
