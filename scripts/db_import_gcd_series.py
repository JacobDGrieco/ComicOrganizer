"""Import issue metadata for one GCD series into the SQLite reading-list database."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from db_common import connect_database

GCD_BASE_URL = "https://www.comics.org/api"


@dataclass(frozen=True)
class ImportIssue:
    gcd_issue_id: str
    issue_number: str
    release_date: str
    release_date_precision: str
    story_arc_id: str
    story_arc_title: str
    source_id: str
    source_url: str


class RateLimitExceeded(RuntimeError):
    def __init__(self, url: str, wait_seconds: float | None):
        self.url = url
        self.wait_seconds = wait_seconds
        message = f"GCD rate limit hit for {url}"
        if wait_seconds is not None:
            message = f"{message}; retry after about {wait_seconds:g}s"
        super().__init__(message)


class RequestBudgetReached(RuntimeError):
    pass


def main() -> int:
    args = parse_args()
    args.network_requests_used = 0
    args.last_fetch_used_network = False
    try:
        series = fetch_json(
            f"{GCD_BASE_URL}/series/{args.gcd_series_id}/?format=json", args
        )
    except RateLimitExceeded as error:
        print(f"WARN {error}")
        return 2
    except RequestBudgetReached as error:
        print(f"WARN {error}")
        return 2

    issue_entries = issue_entries_from_series(
        series, prefilter_descriptors=not args.no_descriptor_prefilter
    )
    if args.limit:
        issue_entries = issue_entries[: args.limit]

    import_issues: list[ImportIssue] = []
    skipped: list[str] = []
    seen_issue_numbers: set[str] = set()

    connection = None if args.dry_run else connect_database(args.db)
    try:
        if connection is not None:
            upsert_universe(connection, args.universe_id)
            upsert_character(connection, args.main_character_id)
            upsert_run_shell(connection, args, series)

        existing_issue_numbers = (
            existing_issue_numbers_for_run(connection, args.run_id)
            if connection is not None
            else set()
        )
        for index, issue_entry in enumerate(issue_entries, start=1):
            descriptor_issue_number = base_issue_number(issue_entry["descriptor"])
            if (
                not args.refresh_existing
                and descriptor_issue_number in existing_issue_numbers
            ):
                skipped.append(f"{descriptor_issue_number}: already imported")
                continue

            try:
                issue = fetch_json(json_url(issue_entry["url"]), args)
            except RateLimitExceeded as error:
                print(f"WARN {error}")
                break
            except RequestBudgetReached as error:
                print(f"WARN {error}")
                break

            if args.delay_seconds and args.last_fetch_used_network:
                time.sleep(args.delay_seconds)

            if should_skip_issue(issue, include_variants=args.include_variants):
                skipped.append(skip_label(issue))
                continue

            try:
                import_issue = to_import_issue(issue, args.story_arc_mode)
            except ValueError as error:
                skipped.append(f"{skip_label(issue)}: {error}")
                continue

            if import_issue.issue_number in seen_issue_numbers:
                skipped.append(
                    f"{skip_label(issue)}: duplicate issue number after base import"
                )
                continue

            seen_issue_numbers.add(import_issue.issue_number)
            import_issues.append(import_issue)
            if connection is not None:
                upsert_issue(connection, args, import_issue)
                connection.commit()
                existing_issue_numbers.add(import_issue.issue_number)

            if args.progress and index % args.progress == 0:
                print(f"Checked {index} GCD issue records...")
    finally:
        if connection is not None:
            connection.close()

    print_summary(series, import_issues, skipped, dry_run=args.dry_run)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import one GCD series into the SQLite reading-list database."
    )
    parser.add_argument("--db", default="database.db", help="SQLite database path.")
    parser.add_argument(
        "--gcd-series-id",
        required=True,
        help="GCD numeric series id, such as 1570 for ASM 1963.",
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Local comic_runs.id to insert/update, such as SER-000002.",
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
        "--story-arc-mode",
        choices=["issue"],
        default="issue",
        help="Initial story arc strategy.",
    )
    parser.add_argument(
        "--limit", type=int, help="Only check the first N GCD issue URLs."
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=6.0,
        help="Delay between issue requests. Defaults to 6.0.",
    )
    parser.add_argument(
        "--max-network-requests",
        type=int,
        default=25,
        help="Stop after N uncached network requests. Defaults to 25.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="Retries for transient failures. Defaults to 0.",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=90.0,
        help="Fallback wait after HTTP 429. Defaults to 90.",
    )
    parser.add_argument(
        "--wait-on-rate-limit",
        action="store_true",
        help="Sleep and retry after HTTP 429 instead of stopping cleanly.",
    )
    parser.add_argument(
        "--cache-dir",
        default=".cache/gcd",
        help="Directory for cached GCD API responses.",
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Disable local API response cache."
    )
    parser.add_argument(
        "--no-descriptor-prefilter",
        action="store_true",
        help="Fetch every GCD issue URL instead of pre-skipping duplicate descriptors.",
    )
    parser.add_argument(
        "--include-variants",
        action="store_true",
        help="Import variants/newsstand/direct editions too.",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Fetch and update issues that are already in the local database.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and report without writing to the database.",
    )
    parser.add_argument(
        "--progress",
        type=int,
        default=50,
        help="Print progress every N checked issue records.",
    )
    return parser.parse_args()


def fetch_json(url: str, args: argparse.Namespace) -> dict[str, Any]:
    args.last_fetch_used_network = False
    cache_path = response_cache_path(url, args)
    if cache_path and cache_path.is_file():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    if (
        args.max_network_requests is not None
        and args.network_requests_used >= args.max_network_requests
    ):
        raise RequestBudgetReached(
            f"Network request budget reached ({args.max_network_requests}). Run the same command again to continue from cache/DB progress."
        )

    args.network_requests_used += 1
    args.last_fetch_used_network = True
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "ComicOrganizer/0.1"}
    )
    for attempt in range(args.max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if cache_path:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(
                        json.dumps(payload, ensure_ascii=True), encoding="utf-8"
                    )
                return payload
        except urllib.error.HTTPError as error:
            if error.code == 429 and not args.wait_on_rate_limit:
                raise RateLimitExceeded(url, retry_after_seconds(error)) from error
            if error.code == 429 and attempt < args.max_retries:
                wait_seconds = retry_after_seconds(error) or args.retry_delay_seconds
                print(
                    f"WARN GCD rate limit hit; waiting {wait_seconds:g}s before retrying {url}"
                )
                time.sleep(wait_seconds)
                continue
            raise RuntimeError(f"Failed to fetch {url}: {error}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt < args.max_retries:
                wait_seconds = min(args.retry_delay_seconds, 10 * (attempt + 1))
                print(
                    f"WARN request failed; waiting {wait_seconds:g}s before retrying {url}: {error}"
                )
                time.sleep(wait_seconds)
                continue
            raise RuntimeError(f"Failed to fetch {url}: {error}") from error

    raise RuntimeError(f"Failed to fetch {url}")


def response_cache_path(url: str, args: argparse.Namespace):
    if args.no_cache:
        return None
    cache_key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return Path(args.cache_dir) / f"{cache_key}.json"


def retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def json_url(url: str) -> str:
    return url if "format=json" in url else f"{url.rstrip('/')}/?format=json"


def issue_entries_from_series(
    series: dict[str, Any], *, prefilter_descriptors: bool
) -> list[dict[str, str]]:
    urls = list(series.get("active_issues", []))
    descriptors = list(series.get("active_issue_descriptors", []))
    if not prefilter_descriptors or len(urls) != len(descriptors):
        return [{"url": url, "descriptor": ""} for url in urls]

    filtered_entries: list[dict[str, str]] = []
    seen_numbers: set[str] = set()
    for url, descriptor in zip(urls, descriptors, strict=True):
        number = base_issue_number(descriptor)
        if number in seen_numbers:
            continue
        seen_numbers.add(number)
        filtered_entries.append({"url": url, "descriptor": number})
    return filtered_entries


def base_issue_number(descriptor: str) -> str:
    return re.sub(r"\s+\[.*\]$", "", str(descriptor)).strip()


def should_skip_issue(issue: dict[str, Any], *, include_variants: bool) -> bool:
    if include_variants:
        return False
    return bool(issue.get("variant_of"))


def to_import_issue(issue: dict[str, Any], story_arc_mode: str) -> ImportIssue:
    gcd_issue_id = api_id(issue["api_url"])
    issue_number = str(issue.get("number") or issue.get("descriptor") or "").strip()
    if not issue_number:
        raise ValueError("missing issue number")

    release_date, release_date_precision = release_date_from_issue(issue)
    if not release_date:
        raise ValueError("missing usable release date")

    story_title = story_arc_title(issue, story_arc_mode)
    return ImportIssue(
        gcd_issue_id=gcd_issue_id,
        issue_number=issue_number,
        release_date=release_date,
        release_date_precision=release_date_precision,
        story_arc_id=f"GCD-ARC-{gcd_issue_id}",
        story_arc_title=story_title,
        source_id=f"GCD-ISS-{gcd_issue_id}",
        source_url=json_url(issue["api_url"]),
    )


def release_date_from_issue(issue: dict[str, Any]) -> tuple[str | None, str]:
    on_sale_date = str(issue.get("on_sale_date") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", on_sale_date):
        return on_sale_date, "day"

    key_date = str(issue.get("key_date") or "").strip()
    year_month_day = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", key_date)
    if not year_month_day:
        return None, "unknown"
    year, month, day = year_month_day.groups()
    if day != "00":
        return key_date, "day"
    if month != "00":
        return f"{year}-{month}", "month"
    return year, "year"


def story_arc_title(issue: dict[str, Any], story_arc_mode: str) -> str:
    if story_arc_mode != "issue":
        raise ValueError(f"unsupported story arc mode: {story_arc_mode}")
    title = str(issue.get("title") or "").strip()
    number = str(issue.get("number") or issue.get("descriptor") or "").strip()
    return (
        title
        or f"{clean_series_name(issue.get('series_name', 'Unknown Series'))} #{number}"
    )


def clean_series_name(value: str) -> str:
    return re.sub(r"\s+\(\d{4} series\)$", "", str(value)).strip()


def api_id(url: str) -> str:
    match = re.search(r"/(\d+)/?(?:\?format=json)?$", url)
    if not match:
        raise ValueError(f"cannot parse GCD id from {url}")
    return match.group(1)


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


def upsert_run_shell(
    connection, args: argparse.Namespace, series: dict[str, Any]
) -> None:
    start_date = str(series.get("year_began") or "0001")
    end_date = str(series.get("year_ended")) if series.get("year_ended") else None
    connection.execute(
        """
		INSERT INTO comic_runs (
			id, title, sort_title, volume, display_volume, publication_type, status, publisher,
			universe_id, start_date, start_date_precision, end_date, end_date_precision, numbering_summary
		)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			title = excluded.title,
			sort_title = excluded.sort_title,
			volume = excluded.volume,
			display_volume = excluded.display_volume,
			publication_type = COALESCE(comic_runs.publication_type, excluded.publication_type),
			status = COALESCE(comic_runs.status, excluded.status),
			publisher = COALESCE(comic_runs.publisher, excluded.publisher),
			numbering_summary = COALESCE(comic_runs.numbering_summary, excluded.numbering_summary)
		""",
        (
            args.run_id,
            series["name"],
            series["name"],
            args.volume,
            f"GCD series {args.gcd_series_id}",
            "Ongoing",
            "Completed" if series.get("year_ended") else "Unknown",
            "Marvel Comics",
            args.universe_id,
            start_date,
            "year",
            end_date,
            "year" if end_date else "unknown",
            series.get("notes"),
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO comic_run_characters (run_id, character_id) VALUES (?, ?)",
        (args.run_id, args.main_character_id),
    )


def upsert_run(
    connection,
    args: argparse.Namespace,
    series: dict[str, Any],
    issues: list[ImportIssue],
) -> None:
    start_date, start_precision = range_edge(
        issues, first=True, fallback_year=series.get("year_began")
    )
    end_date, end_precision = range_edge(
        issues, first=False, fallback_year=series.get("year_ended")
    )
    connection.execute(
        """
		INSERT INTO comic_runs (
			id, title, sort_title, volume, display_volume, publication_type, status, publisher,
			universe_id, start_date, start_date_precision, end_date, end_date_precision, numbering_summary
		)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			title = excluded.title,
			sort_title = excluded.sort_title,
			volume = excluded.volume,
			display_volume = excluded.display_volume,
			publication_type = excluded.publication_type,
			status = excluded.status,
			publisher = excluded.publisher,
			universe_id = excluded.universe_id,
			start_date = excluded.start_date,
			start_date_precision = excluded.start_date_precision,
			end_date = excluded.end_date,
			end_date_precision = excluded.end_date_precision,
			numbering_summary = excluded.numbering_summary
		""",
        (
            args.run_id,
            series["name"],
            series["name"],
            args.volume,
            f"GCD series {args.gcd_series_id}",
            "Ongoing",
            "Completed" if series.get("year_ended") else "Unknown",
            "Marvel Comics",
            args.universe_id,
            start_date,
            start_precision,
            end_date,
            end_precision,
            series.get("notes"),
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO comic_run_characters (run_id, character_id) VALUES (?, ?)",
        (args.run_id, args.main_character_id),
    )


def existing_issue_numbers_for_run(connection, run_id: str) -> set[str]:
    if connection is None:
        return set()
    rows = connection.execute(
        "SELECT issue_number FROM issues WHERE run_id = ?", (run_id,)
    ).fetchall()
    return {row["issue_number"] for row in rows}


def upsert_issue(connection, args: argparse.Namespace, issue: ImportIssue) -> None:
    existing = connection.execute(
        "SELECT id, story_arc_id FROM issues WHERE run_id = ? AND issue_number = ?",
        (args.run_id, issue.issue_number),
    ).fetchone()
    issue_id = existing["id"] if existing else f"GCD-ISS-{issue.gcd_issue_id}"
    story_arc_id = existing["story_arc_id"] if existing else issue.story_arc_id

    connection.execute(
        """
		INSERT INTO sources (id, name, url, source_type)
		VALUES (?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			name = excluded.name,
			url = excluded.url,
			source_type = excluded.source_type
		""",
        (
            issue.source_id,
            "Grand Comics Database",
            issue.source_url,
            "Bibliographic Database",
        ),
    )
    connection.execute(
        """
		INSERT INTO story_arcs (id, title, universe_id, start_date, start_date_precision, end_date, end_date_precision)
		VALUES (?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO NOTHING
		""",
        (
            story_arc_id,
            issue.story_arc_title,
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
			release_date = excluded.release_date,
			release_date_precision = excluded.release_date_precision,
			universe_id = excluded.universe_id
		""",
        (
            issue_id,
            args.run_id,
            issue.issue_number,
            issue.release_date,
            issue.release_date_precision,
            args.universe_id,
            story_arc_id,
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO issue_characters (issue_id, character_id) VALUES (?, ?)",
        (issue_id, args.main_character_id),
    )
    connection.execute(
        "INSERT OR IGNORE INTO issue_sources (issue_id, source_id) VALUES (?, ?)",
        (issue_id, issue.source_id),
    )
    connection.execute(
        "INSERT OR IGNORE INTO story_arc_sources (story_arc_id, source_id) VALUES (?, ?)",
        (story_arc_id, issue.source_id),
    )


def range_edge(
    issues: list[ImportIssue], *, first: bool, fallback_year: int | None
) -> tuple[str, str]:
    if issues:
        ordered = sorted(issues, key=lambda issue: issue.release_date)
        issue = ordered[0] if first else ordered[-1]
        return issue.release_date, issue.release_date_precision
    if fallback_year:
        return str(fallback_year), "year"
    return "0001", "unknown"


def skip_label(issue: dict[str, Any]) -> str:
    return f"{issue.get('series_name', 'series')} #{issue.get('descriptor') or issue.get('number')}"


def print_summary(
    series: dict[str, Any],
    issues: list[ImportIssue],
    skipped: list[str],
    *,
    dry_run: bool,
) -> None:
    mode = "Dry run" if dry_run else "Import"
    print(f"{mode}: {series.get('name')}")
    print(f"Importable base issues: {len(issues)}")
    print(f"Skipped records: {len(skipped)}")
    if skipped[:10]:
        print("First skipped records:")
        for label in skipped[:10]:
            print(f"- {label}")


if __name__ == "__main__":
    raise SystemExit(main())
