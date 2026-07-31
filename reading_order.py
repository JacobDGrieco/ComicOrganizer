"""Read the configured issue-release order from JSON or SQLite."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from issue_numbers import comparable_issue_number, normalize_issue_label, normalize_volume_label
from models import ReadingOrderEntry


class ReadingOrderError(ValueError):
	pass


def read_reading_order(
	reading_order_path: str | Path,
	issue_overrides: dict[str, dict[str, str]] | None = None,
) -> tuple[ReadingOrderEntry, ...]:
	"""Load ordered comic entries and apply configured issue overrides."""
	path = Path(reading_order_path)
	if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
		return read_entries_from_sqlite(path, issue_overrides)

	try:
		raw_order = json.loads(path.read_text(encoding="utf-8"))
	except FileNotFoundError as exc:
		raise ReadingOrderError(f"Reading-order JSON does not exist: {path}") from exc
	except json.JSONDecodeError as exc:
		raise ReadingOrderError(f"Reading-order file is not valid JSON: {path}: {exc}") from exc

	return read_entries_from_json(raw_order, issue_overrides)


def read_entries_from_sqlite(
	reading_order_path: str | Path,
	issue_overrides: dict[str, dict[str, str]] | None = None,
) -> tuple[ReadingOrderEntry, ...]:
	"""Load entries from SQLite using story-arc start date, then issue release date."""
	path = Path(reading_order_path)
	overrides = issue_overrides or {}
	try:
		connection = sqlite3.connect(path)
	except sqlite3.Error as exc:
		raise ReadingOrderError(f"Reading-order SQLite database could not be opened: {path}: {exc}") from exc

	try:
		connection.row_factory = sqlite3.Row
		rows = connection.execute(
			"""
			SELECT
				comic_runs.title AS run,
				comic_runs.volume AS volume,
				issues.issue_number AS issue
			FROM issues
			JOIN comic_runs ON comic_runs.id = issues.cand_id
			JOIN story_arcs ON story_arcs.id = issues.story_arc_id
			ORDER BY
				story_arcs.start_date,
				issues.release_date,
				comic_runs.title,
				CAST(issues.issue_number AS REAL),
				issues.issue_number,
				issues.id
			"""
		).fetchall()
	except sqlite3.Error as exc:
		raise ReadingOrderError(f"Reading-order SQLite query failed: {path}: {exc}") from exc
	finally:
		connection.close()

	entries: list[ReadingOrderEntry] = []
	for position, row in enumerate(rows, start=1):
		run_name = str(row["run"]).strip()
		volume = normalize_volume_label(row["volume"])
		sequence_number = comparable_issue_number(row["issue"])
		issue_label = overrides.get(run_name, {}).get(sequence_number, normalize_issue_label(row["issue"]))
		if not run_name or not volume or not issue_label:
			raise ReadingOrderError(f"Reading-order SQLite row {position} must contain non-empty run, volume, and issue")
		entries.append(ReadingOrderEntry(position=position, run=run_name, volume=volume, issue_label=issue_label))

	return tuple(entries)


def read_entries_from_json(
	raw_order: Any,
	issue_overrides: dict[str, dict[str, str]] | None = None,
) -> tuple[ReadingOrderEntry, ...]:
	"""Convert a JSON array or object with an entries array into ordered entries."""
	overrides = issue_overrides or {}
	raw_entries = _raw_entries(raw_order)
	entries: list[ReadingOrderEntry] = []
	for position, raw_entry in enumerate(raw_entries, start=1):
		if not isinstance(raw_entry, dict):
			raise ReadingOrderError(f"Reading-order entry {position} must be an object")

		run = _entry_value(raw_entry, "run")
		raw_volume = _entry_value(raw_entry, "volume")
		raw_issue = _entry_value(raw_entry, "issue", "issue_label")
		if run is None or raw_volume is None or raw_issue is None:
			raise ReadingOrderError(f"Reading-order entry {position} must contain run, volume, and issue")

		run_name = str(run).strip()
		volume = normalize_volume_label(raw_volume)
		sequence_number = comparable_issue_number(raw_issue)
		issue_label = overrides.get(run_name, {}).get(sequence_number, normalize_issue_label(raw_issue))
		if not run_name or not volume or not issue_label:
			raise ReadingOrderError(f"Reading-order entry {position} must contain non-empty run, volume, and issue")

		entries.append(ReadingOrderEntry(position=position, run=run_name, volume=volume, issue_label=issue_label))

	return tuple(entries)


def _raw_entries(raw_order: Any) -> list[Any]:
	if isinstance(raw_order, list):
		return raw_order
	if not isinstance(raw_order, dict):
		raise ReadingOrderError("Reading-order JSON must be an array or an object with an entries array")

	for key in ("entries", "reading_order", "issue_release_order", "Issue Release Order"):
		value = raw_order.get(key)
		if isinstance(value, list):
			return value

	raise ReadingOrderError("Reading-order JSON object must contain an entries array")


def _entry_value(raw_entry: dict[str, Any], *names: str) -> Any:
	for name in names:
		for key in (name, name.title(), name.replace("_", " ").title()):
			if key in raw_entry:
				return raw_entry[key]

	return None
