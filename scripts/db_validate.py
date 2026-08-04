"""Validate that a ComicOrganizer SQLite database supports organizer reads."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sorting.reading_order import ReadingOrderError, sqlite_reading_order_query


REQUIRED_TABLES = frozenset({"comic_runs", "issues", "story_arcs"})
SQLITE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv)
	try:
		report = validate_database(Path(args.db))
	except ReadingOrderError as exc:
		print(f"ERROR {exc}", file=sys.stderr)
		return 1

	for line in report:
		print(line)
	return 0


def validate_database(database_path: Path) -> list[str]:
	"""Run read-only structural checks and the organizer reading-order query."""
	if database_path.suffix.lower() not in SQLITE_SUFFIXES:
		raise ReadingOrderError(f"Database path must be a SQLite database file: {database_path}")
	if not database_path.is_file():
		raise ReadingOrderError(f"Database file does not exist: {database_path}")

	try:
		database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
		connection = sqlite3.connect(database_uri, uri=True)
	except sqlite3.Error as exc:
		raise ReadingOrderError(f"Database could not be opened read-only: {database_path}: {exc}") from exc

	try:
		connection.row_factory = sqlite3.Row
		existing_tables = {
			str(row["name"])
			for row in connection.execute(
				"SELECT name FROM sqlite_master WHERE type = 'table'"
			)
		}
		missing_tables = sorted(REQUIRED_TABLES - existing_tables)
		if missing_tables:
			raise ReadingOrderError(f"Database is missing required table(s): {', '.join(missing_tables)}")

		counts = {
			table_name: int(connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
			for table_name in sorted(REQUIRED_TABLES)
		}
		reading_order_count = len(connection.execute(sqlite_reading_order_query()).fetchall())
	except sqlite3.Error as exc:
		raise ReadingOrderError(f"Database validation query failed: {database_path}: {exc}") from exc
	finally:
		connection.close()

	return [
		f"Database: {database_path}",
		f"comic_runs: {counts['comic_runs']}",
		f"issues: {counts['issues']}",
		f"story_arcs: {counts['story_arcs']}",
		f"organizer_reading_order_entries: {reading_order_count}",
	]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Validate a ComicOrganizer SQLite database.")
	parser.add_argument("--db", required=True, help="SQLite database path, such as databases/spider-man.db.")
	return parser.parse_args(argv)


if __name__ == "__main__":
	raise SystemExit(main())
