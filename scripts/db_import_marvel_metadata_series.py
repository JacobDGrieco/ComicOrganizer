"""Import a Marvel Metadata API series into the local SQLite reading-list database."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from db_common import connect_database

API_BASE_URL = "https://marvel.emreparker.com/v1"


@dataclass(frozen=True)
class MarvelIssue:
    id: str
    issue_number: str
    title: str
    release_date: str
    release_date_precision: str
    source_url: str


def main() -> int:
    args = parse_args()
    issues = fetch_series_issues(args)
    if args.dry_run:
        print_summary(args, issues, dry_run=True)
        return 0

    with connect_database(args.db) as connection:
        upsert_universe(connection, args.universe_id)
        upsert_character(connection, args.main_character_id)
        upsert_run(connection, args, issues)
        for issue in issues:
            upsert_issue(connection, args, issue)

    print_summary(args, issues, dry_run=False)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import one Marvel Metadata API series into SQLite."
    )
    parser.add_argument("--db", default="database/database.db", help="SQLite database path.")
    parser.add_argument(
        "--marvel-series-id",
        required=True,
        type=int,
        help="Marvel Metadata API series id.",
    )
    parser.add_argument(
        "--run-id", required=True, help="Local comic_runs.id, such as SER-000002."
    )
    parser.add_argument(
        "--volume", default="1", help="Local run volume label. Defaults to 1."
    )
    parser.add_argument(
        "--universe-id",
        default="UNI-000001",
        help="Universe id to assign. Defaults to UNI-000001.",
    )
    parser.add_argument(
        "--main-character-id",
        default="CHAR-PETER-PARKER",
        help="Main character id to assign.",
    )
    parser.add_argument(
        "--run-title", help="Local run title to use when creating a new run."
    )
    parser.add_argument(
        "--limit", type=int, default=200, help="Page size. API maximum is 200."
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.1,
        help="Delay between API requests. Defaults to 1.1.",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Update release dates for already imported issues.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and report without writing to the database.",
    )
    return parser.parse_args()


def fetch_series_issues(args: argparse.Namespace) -> list[MarvelIssue]:
    offset = 0
    issues: list[MarvelIssue] = []
    while True:
        url = f"{API_BASE_URL}/series/{args.marvel_series_id}/issues?limit={args.limit}&offset={offset}"
        payload = fetch_json(url)
        for raw_issue in payload.get("items", []):
            issue = to_issue(raw_issue)
            if issue is not None:
                issues.append(issue)

        if not payload.get("has_next"):
            break
        offset += int(payload.get("limit") or args.limit)
        time.sleep(args.delay_seconds)

    return sorted(
        issues,
        key=lambda issue: (
            issue.release_date,
            comparable_issue_number(issue.issue_number),
            issue.issue_number,
        ),
    )


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "ComicOrganizer/0.1"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def to_issue(raw_issue: dict[str, Any]) -> MarvelIssue | None:
    issue_number = str(raw_issue.get("issueNumber") or "").strip()
    release_date = release_date_from_raw(raw_issue.get("onSaleDate"))
    source_url = str(raw_issue.get("detailUrl") or "").strip()
    if not issue_number or not release_date or not source_url:
        return None

    return MarvelIssue(
        id=f"MM-ISS-{raw_issue['id']}",
        issue_number=issue_number,
        title=str(raw_issue.get("title") or "").strip(),
        release_date=release_date,
        release_date_precision="day",
        source_url=source_url,
    )


def release_date_from_raw(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z").date().isoformat()
    except ValueError:
        match = re.match(r"^\d{4}-\d{2}-\d{2}", text)
        return match.group(0) if match else None


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


def upsert_run(connection, args: argparse.Namespace, issues: list[MarvelIssue]) -> None:
    start_date = issues[0].release_date if issues else "0001"
    end_date = issues[-1].release_date if issues else None
    existing = connection.execute(
        "SELECT title, sort_title FROM comic_runs WHERE id = ?", (args.run_id,)
    ).fetchone()
    title = args.run_title or (
        existing["title"]
        if existing
        else clean_series_title(args.marvel_series_id, issues)
    )
    sort_title = (
        existing["sort_title"] if existing and existing["sort_title"] else title
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
			end_date_precision = excluded.end_date_precision
		""",
        (
            args.run_id,
            title,
            sort_title,
            args.volume,
            f"Marvel Metadata series {args.marvel_series_id}",
            "Ongoing",
            "Unknown",
            "Marvel Comics",
            args.universe_id,
            start_date,
            "day" if issues else "unknown",
            end_date,
            "day" if end_date else "unknown",
            f"Imported from Marvel Metadata API series {args.marvel_series_id}.",
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO comic_run_characters (run_id, character_id) VALUES (?, ?)",
        (args.run_id, args.main_character_id),
    )


def upsert_issue(connection, args: argparse.Namespace, issue: MarvelIssue) -> None:
    source_id = (
        existing_source_id_for_url(connection, issue.source_url)
        or f"MM-SRC-{issue.id.removeprefix('MM-ISS-')}"
    )
    story_arc_id = f"MM-ARC-{issue.id.removeprefix('MM-ISS-')}"
    existing = connection.execute(
        "SELECT id, story_arc_id, release_date, release_date_precision FROM issues WHERE run_id = ? AND issue_number = ?",
        (args.run_id, issue.issue_number),
    ).fetchone()
    issue_id = existing["id"] if existing else issue.id
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
        (source_id, "Marvel Metadata API", issue.source_url, "Metadata API"),
    )
    connection.execute(
        """
		INSERT INTO story_arcs (id, title, universe_id, start_date, start_date_precision, end_date, end_date_precision)
		VALUES (?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO NOTHING
		""",
        (
            story_arc_id,
            issue.title or f"Issue #{issue.issue_number}",
            args.universe_id,
            issue.release_date,
            "day",
            issue.release_date,
            "day",
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


def clean_series_title(series_id: int, issues: list[MarvelIssue]) -> str:
    if not issues:
        return f"Marvel Metadata series {series_id}"
    title = issues[0].title
    return re.sub(r"\s+#.*$", "", title).strip()


def comparable_issue_number(issue_number: str) -> float:
    match = re.match(r"^-?\d+(?:\.\d+)?", issue_number)
    return float(match.group(0)) if match else 0


def print_summary(
    args: argparse.Namespace, issues: list[MarvelIssue], *, dry_run: bool
) -> None:
    mode = "Dry run" if dry_run else "Import"
    print(f"{mode}: Marvel Metadata series {args.marvel_series_id}")
    print(f"Issues: {len(issues)}")
    if issues:
        print(f"First issue: #{issues[0].issue_number} ({issues[0].release_date})")
        print(f"Last issue: #{issues[-1].issue_number} ({issues[-1].release_date})")


if __name__ == "__main__":
    raise SystemExit(main())
