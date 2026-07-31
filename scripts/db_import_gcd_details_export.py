"""Import a GCD series details CSV/JSON export into the local reading-list database."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from db_common import connect_database


@dataclass(frozen=True)
class ExportIssue:
    id: str
    issue_number: str
    release_date: str
    release_date_precision: str
    source_url: str
    raw_number: str
    variant_name: str


def main() -> int:
    args = parse_args()
    records = load_records(args)
    raw_issues = [
        issue for record in records if (issue := to_issue(record, args)) is not None
    ]
    if args.include_variants:
        issues = sorted(
            raw_issues,
            key=lambda issue: (
                date_sort_key(issue.release_date),
                comparable_issue_number(issue.issue_number),
                issue.issue_number,
                issue.id,
            ),
        )
        collapsed_count = 0
    else:
        issues, collapsed_count = collapse_issue_variants(raw_issues)
    if args.expected_count is not None and len(issues) != args.expected_count:
        raise RuntimeError(
            f"Expected {args.expected_count} issues after variant collapse, found {len(issues)}."
        )

    if args.dry_run:
        print_summary(args, issues, collapsed_count, dry_run=True)
        return 0

    with connect_database(args.db) as connection:
        upsert_universe(connection, args.universe_id)
        upsert_character(connection, args.main_character_id)
        upsert_run(connection, args, issues)
        for issue in issues:
            upsert_issue(connection, args, issue)

    print_summary(args, issues, collapsed_count, dry_run=False)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a GCD series details export into SQLite."
    )
    parser.add_argument(
        "--db", default="database.db", help="Local ComicOrganizer SQLite database."
    )
    parser.add_argument(
        "--gcd-series-id", required=True, type=int, help="GCD series id."
    )
    parser.add_argument(
        "--input", help="Local GCD details export file, usually CSV or JSON."
    )
    parser.add_argument(
        "--url",
        help="GCD details export URL. Defaults to the public JSON export endpoint.",
    )
    parser.add_argument(
        "--run-id", required=True, help="Local comic_runs.id value, such as SER-000018."
    )
    parser.add_argument("--run-title", required=True, help="Local run title.")
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
        "--expected-count", type=int, help="Fail if the collapsed issue count differs."
    )
    parser.add_argument(
        "--include-variants",
        action="store_true",
        help="Import duplicate/variant rows instead of collapsing by issue number.",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Update dates for existing imported issues.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.1,
        help="Delay before URL fetch. Useful for batch scripts.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Read and report without writing."
    )
    return parser.parse_args()


def load_records(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.input:
        return load_file(Path(args.input))

    url = (
        args.url
        or f"https://www.comics.org/series/{args.gcd_series_id}/details/?_export=json"
    )
    time.sleep(args.delay_seconds)
    try:
        payload = fetch_url(url)
    except urllib.error.HTTPError as error:
        if error.code == 403:
            raise RuntimeError(
                "GCD blocked the scripted export request with HTTP 403. Download the details export in a browser "
                "and rerun this script with --input."
            ) from error
        raise
    return parse_payload(payload, url)


def load_file(path: Path) -> list[dict[str, Any]]:
    payload = path.read_text(encoding="utf-8-sig")
    return parse_payload(payload, str(path))


def fetch_url(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json,text/csv,text/html;q=0.8,*/*;q=0.5",
            "User-Agent": "ComicOrganizer/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8-sig")


def parse_payload(payload: str, source_name: str) -> list[dict[str, Any]]:
    stripped = payload.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return parse_json_payload(payload)
    if re.search(r"<\s*html|<\s*table", stripped[:500], re.IGNORECASE):
        raise RuntimeError(
            f"{source_name} looks like HTML. Use GCD's CSV or JSON export, not the normal details page."
        )
    return parse_csv_payload(payload)


def parse_json_payload(payload: str) -> list[dict[str, Any]]:
    parsed = json.loads(payload)
    if isinstance(parsed, list):
        return [
            normalize_record(record) for record in parsed if isinstance(record, dict)
        ]
    if isinstance(parsed, dict):
        for key in ("results", "objects", "rows", "items", "data"):
            value = parsed.get(key)
            if isinstance(value, list):
                return [
                    normalize_record(record)
                    for record in value
                    if isinstance(record, dict)
                ]
    return [normalize_record(parsed)]
    raise RuntimeError("Unsupported JSON export shape.")


def parse_csv_payload(payload: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(payload.splitlines())
    return [normalize_record(record) for record in reader]


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {normalize_key(str(key)): value for key, value in record.items()}


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def to_issue(record: dict[str, Any], args: argparse.Namespace) -> ExportIssue | None:
    raw_number = pick(record, "issue", "number", "issue_number")
    issue_number = normalize_issue_number(raw_number)
    release_date, precision = release_date_from_export(
        pick(record, "on_sale", "on_sale_date", "onsale", "release_date"),
        pick(record, "key_date", "sort_date"),
        pick(record, "publication_date", "pub_date", "cover_date"),
    )
    if not issue_number or not release_date:
        return None

    raw_id = pick(record, "id", "issue_id", "gcd_issue_id")
    issue_id = stable_issue_id(args.gcd_series_id, issue_number, raw_id)
    source_url = source_url_for_issue(args, raw_id)
    return ExportIssue(
        id=issue_id,
        issue_number=issue_number,
        release_date=release_date,
        release_date_precision=precision,
        source_url=source_url,
        raw_number=raw_number,
        variant_name=variant_name(raw_number, record),
    )


def pick(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(normalize_key(key))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def normalize_issue_number(raw_number: str) -> str:
    number = raw_number.strip()
    number = re.sub(r"^\s*#", "", number)
    number = re.sub(r"\s+\[[^\]]+\]\s*$", "", number)
    return number.strip()


def release_date_from_export(*candidates: str) -> tuple[str | None, str]:
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text or text in {"-", "—", "?"}:
            continue
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


def stable_issue_id(series_id: int, issue_number: str, raw_id: str) -> str:
    if raw_id and raw_id.isdigit():
        return f"GCD-ISS-{raw_id}"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", issue_number).strip("-").upper()
    return f"GCD-EXPORT-{series_id}-{slug}"


def source_url_for_issue(args: argparse.Namespace, raw_id: str) -> str:
    if raw_id and raw_id.isdigit():
        return f"https://www.comics.org/issue/{raw_id}/"
    return f"https://www.comics.org/series/{args.gcd_series_id}/details/"


def variant_name(raw_number: str, record: dict[str, Any]) -> str:
    explicit = pick(record, "variant", "variant_name")
    if explicit:
        return explicit
    match = re.search(r"\[([^\]]+)\]\s*$", raw_number)
    return match.group(1).strip() if match else ""


def collapse_issue_variants(
    raw_issues: list[ExportIssue],
) -> tuple[list[ExportIssue], int]:
    selected: dict[str, ExportIssue] = {}
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


def issue_sort_key(issue: ExportIssue) -> tuple[int, int, str]:
    variant = issue.variant_name.lower()
    direct_score = 0 if "direct" in variant or "standard" in variant else 1
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


def upsert_run(connection, args: argparse.Namespace, issues: list[ExportIssue]) -> None:
    start_date = issues[0].release_date if issues else "0001"
    end_date = issues[-1].release_date if issues else None
    existing = connection.execute(
        "SELECT sort_title FROM comic_runs WHERE id = ?", (args.run_id,)
    ).fetchone()
    sort_title = (
        existing["sort_title"]
        if existing and existing["sort_title"]
        else args.run_title
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
            args.run_title,
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
            f"Imported from GCD details export series {args.gcd_series_id}. Variants collapsed by issue number.",
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO comic_run_characters (run_id, character_id) VALUES (?, ?)",
        (args.run_id, args.main_character_id),
    )


def upsert_issue(connection, args: argparse.Namespace, issue: ExportIssue) -> None:
    source_id = existing_source_id_for_url(
        connection, issue.source_url
    ) or source_id_for_url(issue.source_url, args.gcd_series_id)
    story_arc_id = f"ARC-{issue.id}"
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
        (source_id, "Grand Comics Database", issue.source_url, "Series Details Export"),
    )
    connection.execute(
        """
		INSERT INTO story_arcs (id, title, universe_id, start_date, start_date_precision, end_date, end_date_precision)
		VALUES (?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO NOTHING
		""",
        (
            story_arc_id,
            issue.raw_number,
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


def source_id_for_url(url: str, series_id: int) -> str:
    match = re.search(r"/issue/(\d+)/", url)
    if match:
        return f"GCD-SRC-{match.group(1)}"
    return f"GCD-DETAILS-SRC-{series_id}"


def print_summary(
    args: argparse.Namespace,
    issues: list[ExportIssue],
    collapsed_count: int,
    *,
    dry_run: bool,
) -> None:
    mode = "Dry run" if dry_run else "Import"
    print(f"{mode}: GCD details export series {args.gcd_series_id}")
    print(f"Issues: {len(issues)}")
    print(f"Collapsed duplicate/variant rows: {collapsed_count}")
    if issues:
        print(f"First issue: #{issues[0].issue_number} ({issues[0].release_date})")
        print(f"Last issue: #{issues[-1].issue_number} ({issues[-1].release_date})")


if __name__ == "__main__":
    raise SystemExit(main())
