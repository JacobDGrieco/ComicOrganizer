"""Read the configured issue-release order from a SQLite database."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .issue_numbers import comparable_issue_number, normalize_issue_label, normalize_volume_label
from .models import ReadingOrderEntry


RECENT_ONGOING_RELEASE_YEAR = 2024
SQLITE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})


class ReadingOrderError(ValueError):
	pass


def read_reading_order(
	reading_order_path: str | Path,
	issue_overrides: dict[str, dict[str, str]] | None = None,
) -> tuple[ReadingOrderEntry, ...]:
	"""Load ordered comic entries from SQLite and apply configured issue overrides."""
	path = Path(reading_order_path)
	if path.suffix.lower() not in SQLITE_SUFFIXES:
		raise ReadingOrderError(f"Reading-order source must be a SQLite database file: {path}")

	return read_entries_from_sqlite(path, issue_overrides)


def read_entries_from_sqlite(
	reading_order_path: str | Path,
	issue_overrides: dict[str, dict[str, str]] | None = None,
) -> tuple[ReadingOrderEntry, ...]:
	"""Load entries from SQLite using the shared organizer reading-order policy."""
	path = Path(reading_order_path)
	if not path.is_file():
		raise ReadingOrderError(f"Reading-order SQLite database does not exist: {path}")

	overrides = issue_overrides or {}
	try:
		connection = sqlite3.connect(path)
	except sqlite3.Error as exc:
		raise ReadingOrderError(f"Reading-order SQLite database could not be opened: {path}: {exc}") from exc

	try:
		connection.row_factory = sqlite3.Row
		rows = connection.execute(sqlite_reading_order_query()).fetchall()
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
		entries.append(
			ReadingOrderEntry(
				position=position,
				run=run_name,
				volume=volume,
				issue_label=issue_label,
				run_years=str(row["years"] or ""),
				run_start_year=_start_year(row["years"]),
				release_date=str(row["release_date"] or ""),
			)
		)

	return tuple(entries)


def sqlite_reading_order_query(*, include_export_fields: bool = False) -> str:
	"""Build the SQLite query used by organizer-facing reading-order commands."""
	extra_fields = """
				story_arcs.title AS story_arc,
				story_arcs.start_date AS story_arc_start_date,
				issues.sort_order AS issue_sort_order,""" if include_export_fields else ""
	return f"""
			SELECT
				comic_runs.title AS run,
				comic_runs.volume AS volume,
				comic_runs.years AS years,
				issues.issue_number AS issue,
{extra_fields}
				issues.release_date AS release_date
			FROM issues
			JOIN comic_runs ON comic_runs.id = issues.cand_id
			JOIN story_arcs ON story_arcs.id = issues.story_arc_id
			ORDER BY
				CASE
					WHEN comic_runs.publication_type = 'Ongoing'
						AND CAST(substr(issues.release_date, 1, 4) AS INTEGER) >= {RECENT_ONGOING_RELEASE_YEAR}
					THEN issues.release_date
					ELSE story_arcs.start_date
				END,
				CASE
					WHEN comic_runs.publication_type = 'Ongoing'
						AND CAST(substr(issues.release_date, 1, 4) AS INTEGER) >= {RECENT_ONGOING_RELEASE_YEAR}
					THEN story_arcs.start_date
					ELSE issues.release_date
				END,
				CASE WHEN issues.sort_order IS NULL THEN 1 ELSE 0 END,
				issues.sort_order,
				comic_runs.title,
				CAST(issues.issue_number AS REAL),
				issues.issue_number,
				issues.id
			"""


def _start_year(years: object) -> str:
	match = re.match(r"^\s*(\d{4})", str(years or ""))
	return match.group(1) if match else ""
