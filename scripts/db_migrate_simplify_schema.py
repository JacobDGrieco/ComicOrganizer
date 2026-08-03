"""Migrate the local SQLite database to the simplified download-focused schema."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from db_common import connect_database, project_root


def main() -> int:
    args = parse_args()
    database_path = Path(args.db)
    if not database_path.exists():
        raise RuntimeError(f"Database not found: {database_path}")

    backup_path = backup_database(database_path)
    temp_path = database_path.with_suffix(
        f".simplified-{datetime.now().strftime('%Y%m%d%H%M%S')}.tmp"
    )
    was_replaced = False
    try:
        migrate_database(database_path, temp_path)
        verify_migration(database_path, temp_path)
        if args.dry_run:
            temp_path.unlink(missing_ok=True)
            print(f"Dry run passed. Backup left at: {backup_path}")
            return 0
        replace_database(temp_path, database_path)
        was_replaced = True
    finally:
        if temp_path.exists() and not args.dry_run and was_replaced:
            temp_path.unlink()

    print(f"Migrated database: {database_path}")
    print(f"Backup: {backup_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simplify the ComicOrganizer SQLite schema."
    )
    parser.add_argument("--db", default="projects/spider-man/database/database.db", help="SQLite database path.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate the migrated database without replacing the original.",
    )
    return parser.parse_args()


def backup_database(database_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = database_path.with_suffix(f".backup-{timestamp}.db")
    shutil.copy2(database_path, backup_path)
    return backup_path


def replace_database(temp_path: Path, database_path: Path) -> None:
    try:
        temp_path.replace(database_path)
    except PermissionError:
        database_path.unlink()
        temp_path.replace(database_path)


def migrate_database(source_path: Path, target_path: Path) -> None:
    if target_path.exists():
        target_path.unlink()
    schema_path = project_root() / "database" / "schema.sql"
    schema_connection = connect_database(target_path)
    try:
        schema_connection.executescript(schema_path.read_text(encoding="utf-8"))
        schema_connection.commit()
    finally:
        schema_connection.close()

    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    target = connect_database(target_path)
    try:
        run_id_mapping = load_run_id_mapping(source)
        copy_comic_runs(source, target)
        copy_story_arcs(source, target)
        copy_issues(source, target, run_id_mapping)
        target.commit()
    finally:
        source.close()
        target.close()


def load_run_id_mapping(source) -> dict[str, str]:
    columns = table_columns(source, "comic_run_candidates")
    if "local_run_id" not in columns:
        return {}
    rows = source.execute("""
		SELECT id, local_run_id
		FROM comic_run_candidates
		WHERE local_run_id IS NOT NULL AND local_run_id != ''
		""").fetchall()
    return {row["local_run_id"]: row["id"] for row in rows}


def table_columns(connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}


def copy_comic_runs(source, target) -> None:
    source_table = (
        "comic_run_candidates"
        if table_exists(source, "comic_run_candidates")
        else "comic_runs"
    )
    source_columns = table_columns(source, source_table)
    for row in source.execute(f"SELECT * FROM {source_table} ORDER BY id"):
        target.execute(
            """
			INSERT INTO comic_runs (
				id, title, volume, years, category, publication_type, universe_hint,
				lead_characters, priority, marvel_url, notes
			)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(id) DO UPDATE SET
				title = excluded.title,
				volume = excluded.volume,
				years = excluded.years,
				category = excluded.category,
				publication_type = excluded.publication_type,
				universe_hint = excluded.universe_hint,
				lead_characters = excluded.lead_characters,
				priority = excluded.priority,
				marvel_url = excluded.marvel_url,
				notes = excluded.notes
			""",
            (
                row["id"],
                row["title"],
                value(row, source_columns, "volume"),
                value(
                    row, source_columns, "years", years_from_dates(row, source_columns)
                ),
                value(row, source_columns, "category", "Imported"),
                value(row, source_columns, "publication_type"),
                value(row, source_columns, "universe_hint"),
                value(row, source_columns, "lead_characters"),
                value(row, source_columns, "priority", "P1"),
                value(row, source_columns, "marvel_url"),
                value(row, source_columns, "notes"),
            ),
        )


def years_from_dates(row, columns: set[str]) -> str | None:
    if "start_date" not in columns:
        return None
    start_date = str(row["start_date"] or "")
    end_date = str(row["end_date"] or "")
    start_year = start_date[:4] if start_date else ""
    end_year = end_date[:4] if end_date else ""
    if start_year and end_year and start_year != end_year:
        return f"{start_year}-{end_year}"
    return start_year or None


def copy_story_arcs(source, target) -> None:
    for row in source.execute("SELECT * FROM story_arcs ORDER BY id"):
        target.execute(
            """
			INSERT INTO story_arcs (id, title, start_date, start_date_precision, end_date, end_date_precision)
			VALUES (?, ?, ?, ?, ?, ?)
			ON CONFLICT(id) DO UPDATE SET
				title = excluded.title,
				start_date = excluded.start_date,
				start_date_precision = excluded.start_date_precision,
				end_date = excluded.end_date,
				end_date_precision = excluded.end_date_precision
			""",
            (
                row["id"],
                row["title"],
                row["start_date"],
                row["start_date_precision"],
                row["end_date"],
                row["end_date_precision"],
            ),
        )


def copy_issues(source, target, run_id_mapping: dict[str, str]) -> None:
    columns = table_columns(source, "issues")
    source_run_column = "cand_id" if "cand_id" in columns else "run_id"
    for row in source.execute("SELECT * FROM issues ORDER BY id"):
        cand_id = row[source_run_column]
        if source_run_column == "run_id":
            cand_id = run_id_mapping.get(cand_id)
            if cand_id is None:
                raise RuntimeError(
                    f"No candidate mapping found for old run_id {row[source_run_column]} used by issue {row['id']}."
                )
        target.execute(
            """
			INSERT INTO issues (id, cand_id, issue_number, release_date, release_date_precision, story_arc_id)
			VALUES (?, ?, ?, ?, ?, ?)
			ON CONFLICT(cand_id, issue_number) DO UPDATE SET
				release_date = excluded.release_date,
				release_date_precision = excluded.release_date_precision,
				story_arc_id = excluded.story_arc_id
			""",
            (
                row["id"],
                cand_id,
                row["issue_number"],
                row["release_date"],
                row["release_date_precision"],
                row["story_arc_id"],
            ),
        )


def value(row, columns: set[str], column: str, default=None):
    return row[column] if column in columns else default


def table_exists(connection, table: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def verify_migration(source_path: Path, target_path: Path) -> None:
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        expected_runs = (
            count_table(source, "comic_run_candidates")
            if table_exists(source, "comic_run_candidates")
            else count_table(source, "comic_runs")
        )
        expected_issues = count_table(source, "issues")
        expected_arcs = count_table(source, "story_arcs")
        actual_runs = count_table(target, "comic_runs")
        actual_issues = count_table(target, "issues")
        actual_arcs = count_table(target, "story_arcs")
        if (expected_runs, expected_issues, expected_arcs) != (
            actual_runs,
            actual_issues,
            actual_arcs,
        ):
            raise RuntimeError(
                "Migration row-count mismatch: "
                f"expected runs/issues/arcs {(expected_runs, expected_issues, expected_arcs)}, "
                f"got {(actual_runs, actual_issues, actual_arcs)}"
            )
    finally:
        source.close()
        target.close()


def count_table(connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


if __name__ == "__main__":
    raise SystemExit(main())
