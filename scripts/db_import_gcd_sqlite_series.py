"""Import one GCD series from a local SQLite dump into the reading-list database."""

from __future__ import annotations

import argparse
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from db_common import connect_database


@dataclass(frozen=True)
class GcdIssue:
    id: int
    issue_number: str
    release_date: str
    release_date_precision: str
    source_url: str
    raw_number: str
    variant_name: str


def main() -> int:
    args = parse_args()
    gcd_connection = connect_gcd_database(args.gcd_db)
    try:
        gcd_columns = inspect_columns(gcd_connection)
        raw_issues = fetch_gcd_issues(gcd_connection, gcd_columns, args)
        issues, collapsed_count = collapse_issue_variants(raw_issues)
        series_title = args.run_title or fetch_series_title(
            gcd_connection, gcd_columns, args.gcd_series_id
        )
    finally:
        gcd_connection.close()

    if args.dry_run:
        print_summary(args, issues, collapsed_count, dry_run=True)
        return 0

    with connect_database(args.db) as connection:
        upsert_universe(connection, args.universe_id)
        upsert_character(connection, args.main_character_id)
        upsert_run(connection, args, series_title, issues)
        for issue in issues:
            upsert_issue(connection, args, issue)

    print_summary(args, issues, collapsed_count, dry_run=False)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import one series from a local GCD SQLite dump."
    )
    parser.add_argument(
        "--db", default="projects/spider-man/database/database.db", help="Local ComicOrganizer SQLite database."
    )
    parser.add_argument(
        "--gcd-db", required=True, help="Path to a downloaded GCD SQLite dump."
    )
    parser.add_argument(
        "--gcd-series-id", required=True, type=int, help="GCD gcd_series.id value."
    )
    parser.add_argument(
        "--run-id", required=True, help="Local comic_runs.id value, such as SER-000018."
    )
    parser.add_argument(
        "--run-title", help="Local run title. Defaults to gcd_series.name."
    )
    parser.add_argument("--volume", default="1", help="Local run volume label.")
    parser.add_argument(
        "--universe-id", default="UNI-000001", help="Universe id to assign."
    )
    parser.add_argument(
        "--main-character-id",
        default="CHAR-PETER-PARKER",
        help="Main character id to assign.",
    )
    parser.add_argument(
        "--include-variants",
        action="store_true",
        help="Import variant rows instead of collapsing to one issue number.",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Update dates for existing imported issues.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Read and report without writing."
    )
    return parser.parse_args()


def connect_gcd_database(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(path))
    connection.row_factory = sqlite3.Row
    return connection


def inspect_columns(connection: sqlite3.Connection) -> dict[str, set[str]]:
    tables = {"gcd_series", "gcd_issue"}
    columns: dict[str, set[str]] = {}
    for table in tables:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"Could not find table {table!r} in the GCD SQLite dump."
            )
        columns[table] = {
            column["name"]
            for column in connection.execute(f"PRAGMA table_info({table})")
        }
    return columns


def fetch_series_title(
    connection: sqlite3.Connection, columns: dict[str, set[str]], series_id: int
) -> str:
    name_column = "name" if "name" in columns["gcd_series"] else None
    if name_column is None:
        return f"GCD series {series_id}"
    row = connection.execute(
        "SELECT name FROM gcd_series WHERE id = ?", (series_id,)
    ).fetchone()
    return str(row["name"]) if row else f"GCD series {series_id}"


def fetch_gcd_issues(
    connection: sqlite3.Connection,
    columns: dict[str, set[str]],
    args: argparse.Namespace,
) -> list[GcdIssue]:
    issue_columns = columns["gcd_issue"]
    required_columns = {"id", "series_id", "number"}
    missing_columns = required_columns - issue_columns
    if missing_columns:
        raise RuntimeError(
            f"GCD dump is missing required gcd_issue columns: {', '.join(sorted(missing_columns))}"
        )

    select_columns = [
        "id",
        "number",
        optional_column(issue_columns, "on_sale_date"),
        optional_column(issue_columns, "publication_date"),
        optional_column(issue_columns, "key_date"),
        optional_column(issue_columns, "variant_name"),
        optional_column(issue_columns, "variant_of_id"),
        optional_column(issue_columns, "sort_code"),
    ]
    query = f"SELECT {', '.join(select_columns)} FROM gcd_issue WHERE series_id = ?"
    parameters: list[Any] = [args.gcd_series_id]
    if "deleted" in issue_columns:
        query += " AND deleted = 0"
    if not args.include_variants and "variant_of_id" in issue_columns:
        query += " AND variant_of_id IS NULL"
    query += " ORDER BY "
    query += "sort_code, id" if "sort_code" in issue_columns else "id"

    issues: list[GcdIssue] = []
    for row in connection.execute(query, parameters):
        issue = to_issue(row)
        if issue is not None:
            issues.append(issue)
    return issues


def optional_column(columns: set[str], name: str) -> str:
    return name if name in columns else f"NULL AS {name}"


def to_issue(row: sqlite3.Row) -> GcdIssue | None:
    raw_number = str(row["number"] or "").strip()
    issue_number = normalize_issue_number(raw_number)
    release_date, precision = release_date_from_gcd(
        row["on_sale_date"], row["publication_date"], row["key_date"]
    )
    if not issue_number or not release_date:
        return None
    issue_id = int(row["id"])
    return GcdIssue(
        id=issue_id,
        issue_number=issue_number,
        release_date=release_date,
        release_date_precision=precision,
        source_url=f"https://www.comics.org/issue/{issue_id}/",
        raw_number=raw_number,
        variant_name=str(row["variant_name"] or "").strip(),
    )


def normalize_issue_number(raw_number: str) -> str:
    number = raw_number.strip()
    number = re.sub(r"^\s*#", "", number)
    number = re.sub(r"\s+\[[^\]]+\]\s*$", "", number)
    return number.strip()


def release_date_from_gcd(*candidates: Any) -> tuple[str | None, str]:
    for candidate in candidates:
        if not candidate:
            continue
        text = str(candidate).strip()
        match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", text)
        if match and match.group(3) != "00":
            return text, "day"
        if match and match.group(2) != "00":
            return f"{match.group(1)}-{match.group(2)}", "month"
        if match:
            return match.group(1), "year"
        month_match = re.match(r"^([A-Za-z]+)\s+(\d{4})$", text)
        if month_match:
            month = month_number(month_match.group(1))
            if month:
                return f"{month_match.group(2)}-{month}", "month"
        year_match = re.match(r"^\[?(\d{4})\]?$", text)
        if year_match:
            return year_match.group(1), "year"
    return None, "unknown"


def month_number(name: str) -> str | None:
    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
    }
    return months.get(name.lower())


def collapse_issue_variants(raw_issues: list[GcdIssue]) -> tuple[list[GcdIssue], int]:
    selected: dict[str, GcdIssue] = {}
    collapsed_count = 0
    for issue in raw_issues:
        existing = selected.get(issue.issue_number)
        if existing is None or issue_sort_key(issue) < issue_sort_key(existing):
            selected[issue.issue_number] = issue
        if existing is not None:
            collapsed_count += 1
    return sorted(
        selected.values(),
        key=lambda issue: (
            date_sort_key(issue.release_date),
            comparable_issue_number(issue.issue_number),
            issue.issue_number,
        ),
    )


def issue_sort_key(issue: GcdIssue) -> tuple[int, int, int]:
    variant_name = issue.variant_name.lower()
    direct_score = 0 if "direct" in variant_name or "standard" in variant_name else 1
    precision_score = {"day": 0, "month": 1, "year": 2, "unknown": 3}.get(
        issue.release_date_precision, 3
    )
    return (precision_score, direct_score, issue.id)


def date_sort_key(value: str) -> str:
    if re.match(r"^\d{4}$", value):
        return f"{value}-99-99"
    if re.match(r"^\d{4}-\d{2}$", value):
        return f"{value}-99"
    return value


def comparable_issue_number(issue_number: str) -> float:
    match = re.match(r"^-?\d+(?:\.\d+)?", issue_number)
    return float(match.group(0)) if match else 0


def upsert_universe(connection, universe_id: str) -> None:
    connection.execute(
        """
		INSERT INTO universes (id, name, display_name)
		VALUES (?, ?, ?)
		ON CONFLICT(id) DO NOTHING
		""",
        (universe_id, universe_id, universe_id),
    )


def upsert_character(connection, character_id: str) -> None:
    connection.execute(
        """
		INSERT INTO characters (id, name)
		VALUES (?, ?)
		ON CONFLICT(id) DO NOTHING
		""",
        (character_id, character_id.removeprefix("CHAR-").replace("-", " ").title()),
    )


def upsert_run(
    connection, args: argparse.Namespace, title: str, issues: list[GcdIssue]
) -> None:
    start_date = issues[0].release_date if issues else "0001"
    end_date = issues[-1].release_date if issues else None
    existing = connection.execute(
        "SELECT title, sort_title FROM comic_runs WHERE id = ?", (args.run_id,)
    ).fetchone()
    run_title = args.run_title or (existing["title"] if existing else title)
    sort_title = (
        existing["sort_title"] if existing and existing["sort_title"] else run_title
    )
    connection.execute(
        """
		INSERT INTO comic_runs (
			id, title, sort_title, volume, display_volume, publication_type, status, publisher,
			universe_id, start_date, start_date_precision, end_date, end_date_precision, numbering_summary
		)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			volume = excluded.volume,
			display_volume = excluded.display_volume,
			start_date = excluded.start_date,
			start_date_precision = excluded.start_date_precision,
			end_date = excluded.end_date,
			end_date_precision = excluded.end_date_precision,
			numbering_summary = excluded.numbering_summary
		""",
        (
            args.run_id,
            run_title,
            sort_title,
            args.volume,
            f"GCD series {args.gcd_series_id}",
            "Ongoing",
            "Unknown",
            "Marvel Comics",
            args.universe_id,
            start_date,
            issues[0].release_date_precision if issues else "unknown",
            end_date,
            issues[-1].release_date_precision if issues else "unknown",
            f"Imported from local GCD SQLite dump series {args.gcd_series_id}. Variants collapsed by issue number.",
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO comic_run_characters (run_id, character_id) VALUES (?, ?)",
        (args.run_id, args.main_character_id),
    )


def upsert_issue(connection, args: argparse.Namespace, issue: GcdIssue) -> None:
    source_id = (
        existing_source_id_for_url(connection, issue.source_url)
        or f"GCD-SRC-{issue.id}"
    )
    story_arc_id = f"GCD-ARC-{issue.id}"
    existing = connection.execute(
        "SELECT id, story_arc_id, release_date, release_date_precision FROM issues WHERE run_id = ? AND issue_number = ?",
        (args.run_id, issue.issue_number),
    ).fetchone()
    issue_id = existing["id"] if existing else f"GCD-ISS-{issue.id}"
    story_arc_id = existing["story_arc_id"] if existing else story_arc_id
    release_date = (
        issue.release_date
        if args.refresh_existing or existing is None
        else existing["release_date"]
    )
    release_date_precision = (
        issue.release_date_precision
        if args.refresh_existing or existing is None
        else existing["release_date_precision"]
    )

    connection.execute(
        """
		INSERT INTO sources (id, name, url, source_type)
		VALUES (?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			name = excluded.name,
			url = excluded.url,
			source_type = excluded.source_type
		""",
        (source_id, "Grand Comics Database", issue.source_url, "Database"),
    )
    connection.execute(
        """
		INSERT INTO story_arcs (id, title, universe_id, start_date, start_date_precision, end_date, end_date_precision)
		VALUES (?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO NOTHING
		""",
        (
            story_arc_id,
            f"{issue.raw_number}",
            args.universe_id,
            issue.release_date,
            issue.release_date_precision,
            issue.release_date,
            issue.release_date_precision,
        ),
    )
    connection.execute(
        """
		INSERT INTO issues (id, run_id, issue_number, release_date, release_date_precision, universe_id, story_arc_id)
		VALUES (?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(run_id, issue_number) DO UPDATE SET
			release_date = CASE WHEN ? THEN excluded.release_date ELSE issues.release_date END,
			release_date_precision = CASE WHEN ? THEN excluded.release_date_precision ELSE issues.release_date_precision END,
			universe_id = excluded.universe_id
		""",
        (
            issue_id,
            args.run_id,
            issue.issue_number,
            release_date,
            release_date_precision,
            args.universe_id,
            story_arc_id,
            1 if args.refresh_existing else 0,
            1 if args.refresh_existing else 0,
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO issue_characters (issue_id, character_id) VALUES (?, ?)",
        (issue_id, args.main_character_id),
    )
    connection.execute(
        "INSERT OR IGNORE INTO issue_sources (issue_id, source_id) VALUES (?, ?)",
        (issue_id, source_id),
    )
    connection.execute(
        "INSERT OR IGNORE INTO story_arc_sources (story_arc_id, source_id) VALUES (?, ?)",
        (story_arc_id, source_id),
    )


def existing_source_id_for_url(connection, url: str) -> str | None:
    row = connection.execute("SELECT id FROM sources WHERE url = ?", (url,)).fetchone()
    return row["id"] if row else None


def print_summary(
    args: argparse.Namespace,
    issues: list[GcdIssue],
    collapsed_count: int,
    *,
    dry_run: bool,
) -> None:
    mode = "Dry run" if dry_run else "Import"
    print(f"{mode}: GCD series {args.gcd_series_id}")
    print(f"Issues: {len(issues)}")
    print(f"Collapsed duplicate/variant rows: {collapsed_count}")
    if issues:
        print(f"First issue: #{issues[0].issue_number} ({issues[0].release_date})")
        print(f"Last issue: #{issues[-1].issue_number} ({issues[-1].release_date})")


if __name__ == "__main__":
    raise SystemExit(main())
