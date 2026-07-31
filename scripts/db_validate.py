"""Validate the local SQLite reading-list database."""

from __future__ import annotations

import argparse

from db_common import connect_database


def main() -> int:
    args = parse_args()
    errors: list[str] = []

    with connect_database(args.db) as connection:
        check_count(connection, errors, "comic_runs")
        check_count(connection, errors, "issues")
        check_count(connection, errors, "story_arcs")
        check_missing(connection, errors)
        check_duplicates(connection, errors)

    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1

    print("Database validation passed.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the Spider-Man SQLite database."
    )
    parser.add_argument("--db", default="database.db", help="SQLite database path.")
    return parser.parse_args()


def check_count(connection, errors: list[str], table: str) -> None:
    count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if count == 0:
        errors.append(f"{table} has no rows")


def check_missing(connection, errors: list[str]) -> None:
    queries = {
        "comic_runs missing titles": "SELECT id FROM comic_runs WHERE title IS NULL OR title = ''",
        "comic_runs missing categories": "SELECT id FROM comic_runs WHERE category IS NULL OR category = ''",
        "issues missing release dates": "SELECT id FROM issues WHERE release_date IS NULL OR release_date = ''",
        "issues missing story arcs": "SELECT id FROM issues WHERE story_arc_id IS NULL OR story_arc_id = ''",
        "story_arcs missing start dates": "SELECT id FROM story_arcs WHERE start_date IS NULL OR start_date = ''",
    }
    for label, query in queries.items():
        rows = connection.execute(query).fetchall()
        if rows:
            errors.append(f"{label}: {', '.join(row['id'] for row in rows)}")


def check_duplicates(connection, errors: list[str]) -> None:
    rows = connection.execute("""
		SELECT cand_id, issue_number, COUNT(*) AS duplicate_count
		FROM issues
		GROUP BY cand_id, issue_number
		HAVING COUNT(*) > 1
		""").fetchall()
    for row in rows:
        errors.append(f"duplicate issue {row['cand_id']} #{row['issue_number']}")


if __name__ == "__main__":
    raise SystemExit(main())
