"""Export the SQLite reading order in the organizer's compact JSON format."""

from __future__ import annotations

import argparse
import json

from db_common import connect_database


def main() -> int:
    args = parse_args()

    with connect_database(args.db) as connection:
        rows = connection.execute("""
			SELECT
				comic_runs.title AS run,
				comic_runs.volume AS volume,
				issues.issue_number AS issue,
				story_arcs.title AS story_arc,
				story_arcs.start_date AS story_arc_start_date,
				issues.release_date AS issue_release_date,
				issues.sort_order AS issue_sort_order
			FROM issues
			JOIN comic_runs ON comic_runs.id = issues.cand_id
			JOIN story_arcs ON story_arcs.id = issues.story_arc_id
			ORDER BY
				story_arcs.start_date,
				issues.release_date,
				CASE WHEN issues.sort_order IS NULL THEN 1 ELSE 0 END,
				issues.sort_order,
				comic_runs.title,
				CAST(issues.issue_number AS REAL),
				issues.issue_number,
				issues.id
			""").fetchall()

    output = {
        "entries": [
            {
                "run": row["run"],
                "volume": row["volume"],
                "issue": row["issue"],
				"story_arc": row["story_arc"],
				"story_arc_start_date": row["story_arc_start_date"],
				"issue_release_date": row["issue_release_date"],
				"issue_sort_order": row["issue_sort_order"],
			}
            for row in rows
        ]
    }
    print(json.dumps(output, indent="\t"))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export SQLite reading order as JSON.")
    parser.add_argument("--db", default="database/database.db", help="SQLite database path.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
