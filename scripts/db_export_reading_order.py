"""Export the SQLite reading order in the organizer's compact JSON format."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Keep direct script execution compatible with package imports from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_common import connect_database
from sorting.reading_order import sqlite_reading_order_query


def main() -> int:
	args = parse_args()

	with connect_database(args.db) as connection:
		rows = connection.execute(sqlite_reading_order_query(include_export_fields=True)).fetchall()

	output = {
		"entries": [
			{
				"run": row["run"],
				"volume": row["volume"],
				"issue": row["issue"],
				"story_arc": row["story_arc"],
				"story_arc_start_date": row["story_arc_start_date"],
				"issue_release_date": row["release_date"],
				"issue_sort_order": row["issue_sort_order"],
			}
			for row in rows
		]
	}
	print(json.dumps(output, indent="\t"))
	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Export SQLite reading order as JSON.")
	parser.add_argument("--db", default="projects/spider-man/database/database.db", help="SQLite database path.")
	return parser.parse_args()


if __name__ == "__main__":
	raise SystemExit(main())
