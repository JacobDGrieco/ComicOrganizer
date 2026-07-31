"""Create the local SQLite database used as the reading-list source of truth."""

from __future__ import annotations

import argparse
from pathlib import Path

from db_common import connect_database, project_root


def main() -> int:
    args = parse_args()
    database_path = Path(args.db)
    schema_path = project_root() / "database" / "schema.sql"

    if args.reset and database_path.exists():
        database_path.unlink()

    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect_database(database_path) as connection:
        connection.executescript(schema_path.read_text(encoding="utf-8"))

    print(f"Initialized SQLite database: {database_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize the Spider-Man SQLite database."
    )
    parser.add_argument("--db", default="database.db", help="SQLite database path.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the target database before initializing it.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
