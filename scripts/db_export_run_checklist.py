"""Export the comic-run queue for download planning."""

from __future__ import annotations

import argparse
import csv
import sys

from db_common import connect_database


def main() -> int:
    args = parse_args()
    with connect_database(args.db) as connection:
        rows = fetch_rows(connection, args)

    if args.format == "markdown":
        print_markdown(rows)
    else:
        print_csv(rows)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export comic runs.")
    parser.add_argument("--db", default="database/database.db", help="SQLite database path.")
    parser.add_argument(
        "--priority",
        action="append",
        help="Filter by priority, such as P0. Can be repeated.",
    )
    parser.add_argument(
        "--category", action="append", help="Filter by category. Can be repeated."
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "csv"],
        default="markdown",
        help="Output format.",
    )
    return parser.parse_args()


def fetch_rows(connection, args: argparse.Namespace):
    query = """
		SELECT id, title, volume, years, category, publication_type, universe_hint, lead_characters,
			priority, marvel_url, marvel_issue_count, notes
		FROM comic_runs
		WHERE 1 = 1
	"""
    parameters: list[str] = []
    if args.priority:
        query += f" AND priority IN ({placeholders(args.priority)})"
        parameters.extend(args.priority)
    if args.category:
        query += f" AND category IN ({placeholders(args.category)})"
        parameters.extend(args.category)
    query += " ORDER BY priority, category, title, volume"
    return connection.execute(query, parameters).fetchall()


def placeholders(values: list[str]) -> str:
    return ", ".join("?" for _ in values)


def print_markdown(rows) -> None:
    current_group = None
    for row in rows:
        group = f"{row['priority']} - {row['category']}"
        if group != current_group:
            if current_group is not None:
                print()
            print(f"## {group}")
            current_group = group
        notes = f" - {row['notes']}" if row["notes"] else ""
        marvel_count = (
            f" - Marvel issues: {row['marvel_issue_count']}"
            if row["marvel_issue_count"] is not None
            else ""
        )
        print(
            f"- {row['title']} vol. {row['volume']} ({row['years']}) [{row['id']}] - {row['publication_type']} - {row['lead_characters']}{marvel_count}{notes}"
        )


def print_csv(rows) -> None:
    fieldnames = [
        "id",
        "title",
        "volume",
        "years",
        "category",
        "publication_type",
        "universe_hint",
        "lead_characters",
        "priority",
        "marvel_url",
        "marvel_issue_count",
        "notes",
    ]
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row[field] for field in fieldnames})


if __name__ == "__main__":
    raise SystemExit(main())
