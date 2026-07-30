# Comic Organizer — Design Spec

Date: 2026-07-30

## Purpose

Reconstruct the previously-built (and since removed) comic organizer tool. It
consolidates comic issues scattered across multiple download-source folders
into a single destination folder, in a specific reading order, renamed to a
canonical filename. First concrete target: the Spider-Man/Spider-Verse
collection, driven by `spider_man_comics_master.xlsx`.

## Background / current state

- **Sources**: Tachidesk downloads at
  `C:\Users\gamin\AppData\Local\Tachidesk\downloads\mangas\<Site> (EN)\<Series Folder>\`.
  Different sites use different filename conventions for the same series:
  - `Issue #N.cbz`
  - `vN NNN.cbz` (volume + zero-padded issue number)
  - `vN .Annual NNN.cbz` (volume + annual + zero-padded issue number)
  Series-folder names don't exactly match the spreadsheet's canonical run
  names (e.g. `Amazing Spider-Man (Publisher_ Marvel)` and
  `The Amazing Spider-Man (1963)` both correspond to spreadsheet run
  `The Amazing Spider-Man`).

- **Reading order source**: `C:\Users\gamin\Downloads\spider_man_comics_master.xlsx`,
  three sheets:
  - `Read Me` — scope/methodology notes.
  - `Comic Runs` — one row per run/volume (Run, Volume, Lead character(s),
    Continuity/universe, Start/End month, Status, Issue count, Notes, Source).
  - `Issue Release Order` — one row per individual issue, generated from each
    run's issue count and pre-sorted chronologically by approximate
    publication month. Row order in this sheet **is** the intended reading
    order (destination position order). Columns include Run, Volume, Issue
    (e.g. `#1`, `#2`...), Ordering note.

  **Known wrinkle**: the `Issue` value in `Issue Release Order` is a
  sequentially generated label per run, not always the real-world/cover issue
  number. E.g. `Amazing Fantasy` has Issue count = 1, so its only row says
  `Issue #1`, but the real comic (and the source filename) is
  `Amazing Fantasy #15`. Confirmed approach: leave the spreadsheet untouched;
  handle exceptions via a config-driven override table, added only for runs
  that actually need correcting.

- **Destination**: `D:\Suwayomi\Comics\Spider-Verse\` already contains 178
  files from a prior (now-removed) tool run, named
  `NNNN - <Canonical Run Name> #<Issue>.cbz` (4-digit zero-padded position
  prefix). Cross-referencing source vs. destination confirms the old tool
  **moved** (not copied) files as it matched them — already-matched source
  files are gone; only not-yet-matched files remain in the source folders.
  Sibling destination folders (`Invincible`, `The Boys`) exist but are out of
  scope for this build (see Scope).

## Scope

This build targets the Spider-Man/Spider-Verse case only. The config format
is generic in shape (paths + mappings, nothing Spider-Man-specific
hardcoded), so reusing the tool later for Invincible/The Boys is a matter of
writing a new config file, not changing code. Multi-character/batch
management in a single run is explicitly out of scope for now.

## Architecture

Python CLI, modular layout (mirrors the previous tool's structure):

- **`config.py`** — loads and validates the JSON config: checks the
  spreadsheet path, destination folder, and each configured source folder
  exist; fails fast with a clear error otherwise.

- **`reading_order.py`** *(replaces the old web-scraper module)* — opens the
  spreadsheet via `openpyxl`, reads the `Issue Release Order` sheet in row
  order, and returns an ordered list of entries:
  `{ position: int, run: str, issue_label: str }` (position = 1-based row
  order in the sheet). Applies `issue_overrides` from config to patch
  specific `(run, sequence_number)` → real issue label before returning.

- **`scanner.py`** — for each entry in the config's `source_folders`, lists
  `.cbz` files in that folder, tagging each with the folder's configured
  `run` name.

- **`parser.py`** — parses each filename into a candidate:
  `{ run: str, issue_number: str, is_annual: bool, raw_name: str }`.
  Recognizes:
  - `Issue #N.cbz` → `issue_number = N`
  - `vN NNN.cbz` → `issue_number = NNN` (leading zeros stripped for
    comparison, e.g. `"010"` → `10`)
  - `vN .Annual NNN.cbz` (punctuation-tolerant match on "annual") →
    `is_annual = True`, `issue_number = NNN`, effective run becomes
    `"{run} Annual"`

- **`matcher.py`** — for each reading-order entry, looks for a parsed
  candidate with matching `run` (Annual-adjusted) and numerically-equal
  issue number. Produces one of:
  - **Matched**: `{ position, canonical_name, source_path }`
  - **Unmatched entry**: no candidate exists yet (not downloaded) → skip
    silently, no error.
  - **Unmatched candidate**: a parsed file whose (run, issue) has no
    corresponding reading-order entry → reported as a warning, left in
    place.
  - **Duplicate candidates**: two+ files match the same reading-order entry
    (e.g. same issue available from two sites) → first one wins, by the
    order its source folder appears in config; the rest are left in place
    and reported as duplicate warnings.

- **`processor.py`** — iterates matches in position order, builds the
  destination filename `NNNN - <Run> #<issue_label>.cbz` (for Annual entries
  the run name already includes "Annual", e.g. `Amazing Spider-Man Annual`),
  skips if a file with that position prefix already exists at the
  destination (safe to rerun), otherwise moves the file via `shutil.move`.
  Catches and reports (not raises) per-file `OSError`s so one failure
  doesn't stop the rest of the run. Colorama output: ✓ moved, ⚠ warning
  (duplicate/unmatched), ✗ move failed, – skipped (already present).
  Supports `dry_run` — same output, no filesystem changes.

- **`organizer.py`** — CLI entry point. `argparse` flags: `--config PATH`
  (default `config.json`), `--dry-run`. Orchestrates: load config → read
  reading order → scan sources → parse → match → process.

## Config schema (JSON)

```json
{
  "spreadsheet_path": "C:\\Users\\gamin\\Downloads\\spider_man_comics_master.xlsx",
  "sheet_name": "Issue Release Order",
  "destination_folder": "D:\\Suwayomi\\Comics\\Spider-Verse",
  "source_folders": [
    {
      "path": "C:\\Users\\gamin\\AppData\\Local\\Tachidesk\\downloads\\mangas\\XOXO Comics (EN)\\Giant-Size Spider-Man",
      "run": "Giant-Size Spider-Man",
      "output_name": "Giant-Size Spider-Man",
      "volume": 1
    },
    {
      "path": "C:\\Users\\gamin\\AppData\\Local\\Tachidesk\\downloads\\mangas\\ReadAllComics (EN)\\Amazing Spider-Man (Publisher_ Marvel)",
      "run": "The Amazing Spider-Man",
      "output_name": "Amazing Spider-Man",
      "volume": 1,
      "annual_run": "Amazing Spider-Man Annual",
      "annual_output_name": "Amazing Spider-Man Annual",
      "annual_volume": 1
    },
    {
      "path": "C:\\Users\\gamin\\AppData\\Local\\Tachidesk\\downloads\\mangas\\ReadComicOnline (EN)\\The Amazing Spider-Man (1963)",
      "run": "The Amazing Spider-Man",
      "output_name": "Amazing Spider-Man",
      "volume": 1
    }
  ],
  "issue_overrides": {
    "Amazing Fantasy": { "1": "15" }
  }
}
```

- `source_folders`: explicit list, one entry per folder. `run` must match the
  spreadsheet's `Run` column and is used for matching. `output_name` is used
  in destination filenames and defaults to `run` when omitted. Multiple
  folders may map to the same run (a series split across sites).
- `volume`: the default spreadsheet `Volume` value for files in that source
  folder. Filename volume tokens such as `v2 001.cbz` override this value for
  that file. It defaults to `1`.
- `annual_run` and `annual_output_name`: optional per-folder overrides for
  files whose names contain an annual marker, useful when annual issues live
  in the same source folder as regular issues but have a different `Run` value
  in the spreadsheet. They default to `<run> Annual` and
  `<output_name> Annual`.
- `annual_volume`: the default spreadsheet `Volume` value for annual files in
  that source folder. Filename volume tokens in annual names override this
  value. It defaults to `volume`.
- `issue_overrides`: keyed by run name, mapping the sheet's generated
  sequence number (as a string key) to the real issue label to use in
  output. Only add entries for runs that actually need correcting.
- Annuals need no override entry for run resolution — they're already a
  distinct `Run` in the spreadsheet (e.g. `Amazing Spider-Man Annual`); the
  parser just needs to detect the annual keyword in the filename and route
  to that run instead of the base series.

## Error handling

- Config validation fails fast (missing spreadsheet, missing destination
  folder, any configured source folder missing, malformed JSON) with a
  clear message, before any file operations occur.
- Per-file move failures (`OSError`, e.g. file locked/in use) are caught,
  reported, and don't halt the rest of the run.
- Dry-run mode is available and recommended for the first real run against
  live data — shows every planned move with no filesystem changes.

## Testing

Unit tests per module, mirroring the previous tool's test suite:

- `config.py` — valid/invalid config loading, missing-path validation.
- `reading_order.py` — sheet parsing into ordered entries, override
  application.
- `parser.py` — all three filename patterns, annual detection, leading-zero
  handling.
- `matcher.py` — matched/unmatched-entry/unmatched-candidate/duplicate
  cases.
- `processor.py` — move logic, skip-if-already-present, dry-run (no
  filesystem changes), per-file failure isolation.

Manual/integration pass: run against the real Spider-Verse config with
`--dry-run` first, review the planned move list, then run for real.
