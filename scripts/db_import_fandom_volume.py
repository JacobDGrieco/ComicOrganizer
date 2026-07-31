"""Import issue rows from a Marvel Fandom volume page into the simplified catalog."""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from db_common import connect_database

FANDOM_API_URL = "https://marvel.fandom.com/api.php"
MONTH_PRECISION_FORMATS = ("%B %Y", "%b %Y")
DAY_PRECISION_FORMATS = ("%B %d, %Y", "%b %d, %Y")


@dataclass(frozen=True)
class FandomIssue:
	id: str
	issue_number: str
	release_date: str
	release_date_precision: str
	display_title: str
	source_page: str


@dataclass(frozen=True)
class RunScope:
	id: str
	title: str
	years: str
	marvel_url: str
	marvel_issue_count: int | None
	start_year: int | None
	end_year: int | None


def main() -> int:
	args = parse_args()
	with connect_database(args.db) as connection:
		run_scope = fetch_run_scope(connection, args.run_id)

	raw_issues = fetch_fandom_issues(
		args.fandom_page, args.delay_seconds, args.issue_number
	)
	issues = filter_issues_by_scope(
		raw_issues, run_scope, args.no_year_filter, args.start_year_grace
	)
	issues = filter_issues_by_max_release_date(issues, args.max_release_date)
	if args.expected_count is not None and len(issues) != args.expected_count:
		raise RuntimeError(
			f"Expected {args.expected_count} issues after filtering, found {len(issues)}."
		)

	if args.dry_run:
		print_summary(args, run_scope, raw_issues, issues, dry_run=True)
		return 0

	with connect_database(args.db) as connection:
		for issue in issues:
			upsert_issue(connection, args, run_scope, issue)
		append_import_note(connection, args, run_scope, issues)

	print_summary(args, run_scope, raw_issues, issues, dry_run=False)
	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Import one Marvel Fandom volume page into the simplified SQLite catalog."
	)
	parser.add_argument("--db", default="database/database.db", help="SQLite database path.")
	parser.add_argument("--run-id", required=True, help="Existing comic_runs.id value.")
	parser.add_argument(
		"--fandom-page",
		required=True,
		help="Marvel Fandom volume page, such as Spider-Man_Vol_1.",
	)
	parser.add_argument(
		"--expected-count",
		type=int,
		help="Fail if the filtered Fandom issue count differs from this value.",
	)
	parser.add_argument(
		"--refresh-existing",
		action="store_true",
		help="Update release dates for existing issue rows.",
	)
	parser.add_argument(
		"--no-year-filter",
		action="store_true",
		help="Import every dated Fandom issue even when outside comic_runs.years.",
	)
	parser.add_argument(
		"--start-year-grace",
		type=int,
		default=1,
		help="Allow issues released this many years before comic_runs.years starts. Defaults to 1 for advance-shipped comics.",
	)
	parser.add_argument(
		"--delay-seconds",
		type=float,
		default=0.5,
		help="Delay before fetching Fandom. Useful for batch imports.",
	)
	parser.add_argument(
		"--max-release-date",
		help="Import only issues released on or before this ISO date, such as 2026-07-31.",
	)
	parser.add_argument(
		"--issue-number",
		help="Use this issue number when --fandom-page points directly at a single issue page.",
	)
	parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
	return parser.parse_args()


def fetch_run_scope(connection, run_id: str) -> RunScope:
	row = connection.execute(
		"""
		SELECT id, title, years, marvel_url, marvel_issue_count
		FROM comic_runs
		WHERE id = ?
		""",
		(run_id,),
	).fetchone()
	if row is None:
		raise RuntimeError(f"Run not found: {run_id}")
	start_year, end_year = parse_year_range(row["years"] or "")
	return RunScope(
		id=row["id"],
		title=row["title"],
		years=row["years"] or "",
		marvel_url=row["marvel_url"] or "",
		marvel_issue_count=row["marvel_issue_count"],
		start_year=start_year,
		end_year=end_year,
	)


def parse_year_range(years: str) -> tuple[int | None, int | None]:
	match = re.match(r"^\s*(\d{4})(?:\s*-\s*(\d{4})?)?\s*$", years)
	if not match:
		return None, None
	start_year = int(match.group(1))
	has_range_separator = "-" in years
	if match.group(2):
		end_year = int(match.group(2))
	elif has_range_separator:
		end_year = None
	else:
		end_year = start_year
	return start_year, end_year


def fetch_fandom_issues(
	page: str, delay_seconds: float, issue_number_override: str | None
) -> list[FandomIssue]:
	time.sleep(delay_seconds)
	page_title, page_html, page_wikitext = fetch_fandom_page(page)
	issues = dedupe_issues(parse_issue_cards(page_title, page_html))
	if not issues:
		issue = issue_from_wikitext_page(
			page_title, page_wikitext, issue_number_override
		)
		if issue is not None:
			issues = [issue]
	return sorted(
		issues,
		key=lambda issue: (
			date_sort_key(issue.release_date),
			comparable_issue_number(issue.issue_number),
			issue.issue_number,
		),
	)


def fetch_fandom_page(page: str) -> tuple[str, str, str]:
	query = urllib.parse.urlencode(
		{
			"action": "parse",
			"page": page.replace(" ", "_"),
			"prop": "text|wikitext",
			"format": "json",
			"disableeditsection": "1",
		}
	)
	request = urllib.request.Request(
		f"{FANDOM_API_URL}?{query}",
		headers={"Accept": "application/json", "User-Agent": "ComicOrganizer/0.1"},
	)
	with urllib.request.urlopen(request, timeout=30) as response:
		payload = json.loads(response.read().decode("utf-8"))
	if "error" in payload:
		raise RuntimeError(
			f"Fandom returned {payload['error'].get('code')}: {payload['error'].get('info')}"
		)
	parsed = payload.get("parse") or {}
	return (
		str(parsed.get("title") or page),
		str((parsed.get("text") or {}).get("*") or ""),
		str((parsed.get("wikitext") or {}).get("*") or ""),
	)


def parse_issue_cards(page_title: str, page_html: str) -> list[FandomIssue]:
	issues: list[FandomIssue] = []
	for alt_text in image_alt_texts(page_html):
		issue = issue_from_alt_text(page_title, alt_text)
		if issue is not None:
			issues.append(issue)
	return issues


def image_alt_texts(page_html: str) -> list[str]:
	return [
		html.unescape(match.group(1))
		for match in re.finditer(r'\salt="([^"]*)"', page_html)
	]


def issue_from_alt_text(page_title: str, alt_text: str) -> FandomIssue | None:
	text = re.sub(r"\s+", " ", alt_text).strip()
	if "#" not in text or "Release date:" not in text:
		return None
	text = re.sub(r"^(Available|Unavailable)\s+", "", text)
	match = re.match(
		r"(?P<series>.+?)\s+#(?P<number>.+?)(?:\s+\"(?P<title>[^\"]*)\"|\s+Release date:)",
		text,
	)
	if match is None:
		return None
	date_match = re.search(r"Release date:\s*(?P<date>.*?)(?:\s+Cover date:|$)", text)
	if date_match is None:
		return None
	release_date, precision = parse_fandom_date(date_match.group("date"))
	if release_date is None:
		return None
	issue_number = normalize_issue_number(match.group("number"))
	if not issue_number:
		return None
	return FandomIssue(
		id=f"FANDOM-ISS-{slugify(page_title)}-{slugify_issue_number(issue_number)}",
		issue_number=issue_number,
		release_date=release_date,
		release_date_precision=precision,
		display_title=match.group("title") or "",
		source_page=page_title,
	)


def issue_from_wikitext_page(
	page_title: str, page_wikitext: str, issue_number_override: str | None
) -> FandomIssue | None:
	if "Comic Template" not in page_wikitext:
		return None
	release_date, precision = parse_fandom_date(
		template_field(page_wikitext, "ReleaseDate")
	)
	if release_date is None:
		release_date, precision = parse_fandom_date(
			template_field(page_wikitext, "Year")
		)
	if release_date is None:
		return None
	issue_number = normalize_issue_number(
		issue_number_override or issue_number_from_page_title(page_title) or "1"
	)
	return FandomIssue(
		id=f"FANDOM-ISS-{slugify(page_title)}-{slugify_issue_number(issue_number)}",
		issue_number=issue_number,
		release_date=release_date,
		release_date_precision=precision,
		display_title=template_field(page_wikitext, "StoryTitle1"),
		source_page=page_title,
	)


def template_field(page_wikitext: str, field_name: str) -> str:
	pattern = rf"(?m)^\|\s*{re.escape(field_name)}\s*=\s*(.*?)\s*$"
	match = re.search(pattern, page_wikitext)
	return match.group(1).strip() if match else ""


def issue_number_from_page_title(page_title: str) -> str | None:
	match = re.search(r"\bVol\s+\d+\s+([^:]+)$", page_title)
	return match.group(1).strip() if match else None


def normalize_issue_number(issue_number: str) -> str:
	return (
		issue_number.strip()
		.replace("½", "1/2")
		.replace("¼", "1/4")
		.replace("¾", "3/4")
	)


def parse_fandom_date(raw_date: str) -> tuple[str | None, str]:
	text = raw_date.strip()
	if not text or text.lower() in {"unknown", "unreleased"}:
		return None, "unknown"
	for date_format in DAY_PRECISION_FORMATS:
		try:
			return datetime.strptime(text, date_format).date().isoformat(), "day"
		except ValueError:
			pass
	for date_format in MONTH_PRECISION_FORMATS:
		try:
			return datetime.strptime(text, date_format).strftime("%Y-%m"), "month"
		except ValueError:
			pass
	year_match = re.match(r"^(\d{4})$", text)
	if year_match:
		return year_match.group(1), "year"
	return None, "unknown"


def dedupe_issues(issues: list[FandomIssue]) -> list[FandomIssue]:
	selected: dict[str, FandomIssue] = {}
	for issue in issues:
		existing = selected.get(issue.issue_number)
		if existing is None or issue.release_date < existing.release_date:
			selected[issue.issue_number] = issue
	return list(selected.values())


def filter_issues_by_scope(
	issues: list[FandomIssue],
	run_scope: RunScope,
	no_year_filter: bool,
	start_year_grace: int,
) -> list[FandomIssue]:
	if no_year_filter or run_scope.start_year is None:
		return issues
	filtered: list[FandomIssue] = []
	minimum_year = run_scope.start_year - max(start_year_grace, 0)
	for issue in issues:
		issue_year = int(issue.release_date[:4])
		if issue_year < minimum_year:
			continue
		if run_scope.end_year is not None and issue_year > run_scope.end_year:
			continue
		filtered.append(issue)
	return filtered


def filter_issues_by_max_release_date(
	issues: list[FandomIssue], max_release_date: str | None
) -> list[FandomIssue]:
	if not max_release_date:
		return issues
	validate_iso_date(max_release_date)
	return [
		issue
		for issue in issues
		if date_sort_key(issue.release_date) <= date_sort_key(max_release_date)
	]


def validate_iso_date(value: str) -> None:
	if not re.match(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$", value):
		raise RuntimeError(f"Invalid --max-release-date value: {value}")


def upsert_issue(
	connection, args: argparse.Namespace, run_scope: RunScope, issue: FandomIssue
) -> None:
	run_slug = slugify(run_scope.id)
	issue_number_slug = slugify_issue_number(issue.issue_number)
	story_arc_id = f"LOCAL-ARC-{run_slug}-{slugify(issue.source_page)}-{issue_number_slug}"
	story_title = f"{run_scope.title} #{issue.issue_number}"
	existing = connection.execute(
		"""
		SELECT id, story_arc_id, release_date, release_date_precision
		FROM issues
		WHERE cand_id = ? AND issue_number = ?
		""",
		(args.run_id, issue.issue_number),
	).fetchone()
	issue_id = (
		existing["id"]
		if existing
		else stable_issue_id(args.run_id, issue.issue_number)
	)
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
		INSERT INTO story_arcs (
			id, title, start_date, start_date_precision, end_date, end_date_precision
		)
		VALUES (?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			title = excluded.title,
			start_date = excluded.start_date,
			start_date_precision = excluded.start_date_precision,
			end_date = excluded.end_date,
			end_date_precision = excluded.end_date_precision
		""",
		(
			story_arc_id,
			story_title,
			issue.release_date,
			issue.release_date_precision,
			issue.release_date,
			issue.release_date_precision,
		),
	)
	connection.execute(
		"""
		INSERT INTO issues (
			id, cand_id, issue_number, release_date, release_date_precision, story_arc_id
		)
		VALUES (?, ?, ?, ?, ?, ?)
		ON CONFLICT(cand_id, issue_number) DO UPDATE SET
			release_date = CASE WHEN ? THEN excluded.release_date ELSE issues.release_date END,
			release_date_precision = CASE WHEN ? THEN excluded.release_date_precision ELSE issues.release_date_precision END
		""",
		(
			issue_id,
			args.run_id,
			issue.issue_number,
			release_date,
			release_date_precision,
			story_arc_id,
			1 if args.refresh_existing else 0,
			1 if args.refresh_existing else 0,
		),
	)


def append_import_note(
	connection, args: argparse.Namespace, run_scope: RunScope, issues: list[FandomIssue]
) -> None:
	if not issues:
		return
	note = (
		f"Issues imported from Marvel Fandom page {args.fandom_page}; "
		f"official Marvel series page: {run_scope.marvel_url or 'not recorded'}."
	)
	existing = connection.execute(
		"SELECT notes FROM comic_runs WHERE id = ?", (args.run_id,)
	).fetchone()
	existing_notes = existing["notes"] if existing and existing["notes"] else ""
	if note in existing_notes:
		return
	combined = f"{existing_notes} {note}".strip() if existing_notes else note
	connection.execute(
		"UPDATE comic_runs SET notes = ? WHERE id = ?", (combined, args.run_id)
	)


def date_sort_key(value: str) -> str:
	if re.match(r"^\d{4}$", value):
		return f"{value}-99-99"
	if re.match(r"^\d{4}-\d{2}$", value):
		return f"{value}-99"
	return value


def comparable_issue_number(issue_number: str) -> tuple[float, str]:
	match = re.match(r"^-?\d+(?:\.\d+)?", issue_number)
	number = float(match.group(0)) if match else 0
	return number, issue_number


def slugify(value: str) -> str:
	slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
	return slug or "UNKNOWN"


def slugify_issue_number(issue_number: str) -> str:
	value = issue_number.strip().upper()
	value = value.replace("-", "NEG-")
	value = value.replace("/", "-SLASH-")
	value = value.replace(".", "-POINT-")
	return slugify(value)


def stable_issue_id(run_id: str, issue_number: str) -> str:
	return f"FANDOM-ISS-{slugify(run_id)}-{slugify_issue_number(issue_number)}"


def print_summary(
	args: argparse.Namespace,
	run_scope: RunScope,
	raw_issues: list[FandomIssue],
	issues: list[FandomIssue],
	*,
	dry_run: bool,
) -> None:
	mode = "Dry run" if dry_run else "Import"
	print(f"{mode}: {run_scope.title} [{run_scope.id}]")
	print(f"Fandom page: https://marvel.fandom.com/wiki/{args.fandom_page}")
	print(f"Official Marvel page: {run_scope.marvel_url or 'not recorded'}")
	print(f"Official Marvel issue count: {run_scope.marvel_issue_count}")
	print(f"Fandom dated issues found: {len(raw_issues)}")
	print(f"Imported after year filter ({run_scope.years or 'unscoped'}): {len(issues)}")
	if args.max_release_date:
		print(f"Max release date: {args.max_release_date}")
	if issues:
		print(f"First issue: #{issues[0].issue_number} ({issues[0].release_date})")
		print(f"Last issue: #{issues[-1].issue_number} ({issues[-1].release_date})")


if __name__ == "__main__":
	raise SystemExit(main())
