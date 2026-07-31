"""Audit comic run coverage against stored Marvel counts and Marvel Fandom issue lists."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from db_common import connect_database, project_root
from db_import_fandom_volume import fetch_fandom_issues

MARVEL_METADATA_API = "https://marvel.emreparker.com/v1"
INCLUDE_PATTERNS = [
	r"spider",
	r"spider-man",
	r"spider-gwen",
	r"spider-girl",
	r"spider-boy",
	r"spider-punk",
	r"spider-ham",
	r"scarlet spider",
	r"venom",
	r"carnage",
	r"symbi",
	r"knull",
	r"queen in black",
	r"silk",
	r"miles morales",
	r"ghost-spider",
]
EXCLUDE_PATTERNS = [
	r"facsimile",
	r"variant",
	r"trade paperback",
	r"hardcover",
	r"omnibus",
	r"epic collection",
	r"masterworks",
	r"complete collection",
	r"collection",
	r"modern era epic collection",
	r"digest",
	r"poster",
	r"spanish language",
	r"sketchbook",
	r"premiere comic",
	r"director'?s cut",
	r"\btpb\b",
	r"\bhc\b",
	r"\bbook\s+\d+",
	r"\bvol\.\s*\d+\s*:",
	r"\bessential\b",
	r"true believers",
	r"marvel tales",
	r"primer",
]
WATCH_PATTERNS = [
	r"annual",
	r"one-shot",
	r"alpha",
	r"omega",
	r"special",
	r"giant-size",
	r"giant size",
	r"fcbd",
	r"free comic book day",
	r"anthology",
	r"family",
	r"unlimited",
	r"infinity comic",
	r"infinite comic",
]


@dataclass(frozen=True)
class RunRow:
	id: str
	title: str
	volume: str
	years: str
	category: str
	publication_type: str
	priority: str
	marvel_url: str
	marvel_issue_count: int | None
	notes: str
	db_issue_numbers: frozenset[str]


@dataclass(frozen=True)
class FandomCheck:
	page: str
	status: str
	issue_numbers: tuple[str, ...]
	error: str = ""


@dataclass(frozen=True)
class MarvelSeries:
	id: int
	name: str
	issue_count: int | None


def main() -> int:
	args = parse_args()
	with connect_database(args.db) as connection:
		runs = fetch_runs(connection, args.priority)

	fandom_checks: dict[str, FandomCheck] = {}
	report_lines = build_report(args, runs, fandom_checks)
	output_path = Path(args.output)
	if not output_path.is_absolute():
		output_path = project_root() / output_path
	output_path.parent.mkdir(parents=True, exist_ok=True)
	output_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
	print(f"Wrote coverage audit: {output_path}")
	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Audit issue coverage by priority.")
	parser.add_argument("--db", default="database/database.db", help="SQLite database path.")
	parser.add_argument(
		"--priority",
		action="append",
		help="Priority to include, such as P0. Can be repeated; defaults to all.",
	)
	parser.add_argument(
		"--output",
		default="docs/database/coverage-audit.md",
		help="Markdown report path.",
	)
	parser.add_argument(
		"--fandom",
		action="store_true",
		help="Fetch Marvel Fandom issue lists and compare issue numbers.",
	)
	parser.add_argument(
		"--fandom-scope",
		choices=("notes", "infer"),
		default="notes",
		help="Use only recorded Fandom pages from notes, or infer Fandom page names for every run.",
	)
	parser.add_argument(
		"--cache-dir",
		default=".cache/fandom-coverage-audit",
		help="Directory for cached Fandom issue-list checks.",
	)
	parser.add_argument(
		"--discover-marvel-series",
		action="store_true",
		help="Fetch Marvel metadata series index for missing Spider-related run candidates.",
	)
	parser.add_argument(
		"--delay-seconds",
		type=float,
		default=0.25,
		help="Delay between uncached network requests.",
	)
	return parser.parse_args()


def fetch_runs(connection, priorities: list[str] | None) -> list[RunRow]:
	conditions: list[str] = []
	parameters: list[str] = []
	if priorities:
		placeholders = ",".join("?" for _ in priorities)
		conditions.append(f"comic_runs.priority IN ({placeholders})")
		parameters.extend(priorities)
	where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
	rows = connection.execute(
		f"""
		SELECT
			comic_runs.id,
			comic_runs.title,
			COALESCE(comic_runs.volume, '') AS volume,
			COALESCE(comic_runs.years, '') AS years,
			comic_runs.category,
			COALESCE(comic_runs.publication_type, '') AS publication_type,
			comic_runs.priority,
			COALESCE(comic_runs.marvel_url, '') AS marvel_url,
			comic_runs.marvel_issue_count,
			COALESCE(comic_runs.notes, '') AS notes,
			GROUP_CONCAT(issues.issue_number, '||') AS issue_numbers
		FROM comic_runs
		LEFT JOIN issues ON issues.cand_id = comic_runs.id
		{where_clause}
		GROUP BY comic_runs.id
		ORDER BY comic_runs.priority, comic_runs.category, comic_runs.title, CAST(comic_runs.volume AS REAL), comic_runs.volume
		""",
		parameters,
	).fetchall()
	return [
		RunRow(
			id=row["id"],
			title=row["title"],
			volume=str(row["volume"]),
			years=str(row["years"]),
			category=row["category"],
			publication_type=str(row["publication_type"]),
			priority=row["priority"],
			marvel_url=str(row["marvel_url"]),
			marvel_issue_count=row["marvel_issue_count"],
			notes=str(row["notes"]),
			db_issue_numbers=frozenset(
				number for number in str(row["issue_numbers"] or "").split("||") if number
			),
		)
		for row in rows
	]


def build_report(
	args: argparse.Namespace,
	runs: list[RunRow],
	fandom_checks: dict[str, FandomCheck],
) -> list[str]:
	lines = [
		"# Coverage Audit",
		"",
		"Research cutoff: 2026-07-31",
		"",
		"Sources:",
		"- Stored `comic_runs.marvel_url` and `comic_runs.marvel_issue_count` values from official Marvel research.",
		"- Marvel Fandom issue-list pages when `--fandom` is enabled.",
		"- Marvel metadata series index discovery when `--discover-marvel-series` is enabled.",
		"",
	]
	append_summary(lines, runs)
	append_count_gaps(lines, runs)
	if args.fandom:
		append_fandom_gaps(lines, runs, fandom_checks, args)
	append_negative_issues(lines, runs)
	append_watchlist(lines, runs)
	if args.discover_marvel_series:
		append_missing_marvel_series(lines, runs, args.delay_seconds)
	return lines


def append_summary(lines: list[str], runs: list[RunRow]) -> None:
	lines.extend(["## Summary", ""])
	for priority in sorted({run.priority for run in runs}):
		priority_runs = [run for run in runs if run.priority == priority]
		issue_rows = sum(len(run.db_issue_numbers) for run in priority_runs)
		marvel_expected = sum(run.marvel_issue_count or 0 for run in priority_runs)
		lines.append(
			f"- `{priority}`: {len(priority_runs)} runs, {issue_rows} issue rows, "
			f"{marvel_expected} stored Marvel-count issues."
		)
	lines.append("")


def append_count_gaps(lines: list[str], runs: list[RunRow]) -> None:
	lines.extend(["## Stored Marvel Count Gaps", ""])
	gap_rows = [
		run
		for run in runs
		if run.marvel_issue_count is not None and len(run.db_issue_numbers) != run.marvel_issue_count
	]
	if not gap_rows:
		lines.extend(["No stored Marvel count gaps found.", ""])
		return
	for run in gap_rows:
		delta = len(run.db_issue_numbers) - int(run.marvel_issue_count or 0)
		lines.append(
			f"- `{run.priority}` `{run.id}` {run.title} vol. {run.volume or '?'} ({run.years or '?'}) "
			f"[{run.publication_type or 'unknown'}]: DB {len(run.db_issue_numbers)} vs Marvel {run.marvel_issue_count} "
			f"(delta {delta:+d})"
		)
	lines.append("")


def append_fandom_gaps(
	lines: list[str],
	runs: list[RunRow],
	fandom_checks: dict[str, FandomCheck],
	args: argparse.Namespace,
) -> None:
	lines.extend(["## Fandom Issue-List Gaps", ""])
	checked = 0
	missing_sections = 0
	for run in runs:
		check = check_fandom_run(run, fandom_checks, args)
		if check.status == "missing-page":
			continue
		checked += 1
		if check.status != "ok":
			lines.append(
				f"- `{run.priority}` `{run.id}` {run.title} vol. {run.volume or '?'}: "
				f"Fandom check failed for `{check.page}`: {check.error}"
			)
			continue
		fandom_numbers = frozenset(check.issue_numbers)
		missing = sorted_issue_numbers(fandom_numbers - run.db_issue_numbers)
		extra = sorted_issue_numbers(run.db_issue_numbers - fandom_numbers)
		if not missing and not extra:
			continue
		missing_sections += 1
		lines.append(
			f"- `{run.priority}` `{run.id}` {run.title} vol. {run.volume or '?'} "
			f"via `{check.page}`: DB {len(run.db_issue_numbers)} vs Fandom {len(fandom_numbers)}"
		)
		if missing:
			lines.append(f"  - Missing in DB: {', '.join(missing[:80])}{ellipsis(missing, 80)}")
		if extra:
			lines.append(f"  - Extra in DB: {', '.join(extra[:80])}{ellipsis(extra, 80)}")
	if checked == 0:
		lines.append("No Fandom pages were resolved for the selected runs.")
	elif missing_sections == 0:
		lines.append(f"Checked {checked} Fandom pages; no issue-number gaps found.")
	lines.append("")


def check_fandom_run(
	run: RunRow,
	fandom_checks: dict[str, FandomCheck],
	args: argparse.Namespace,
) -> FandomCheck:
	pages = fandom_page_candidates(run, infer=args.fandom_scope == "infer")
	for page in pages:
		if page in fandom_checks:
			check = fandom_checks[page]
		else:
			check = fetch_fandom_check(page, args.delay_seconds, Path(args.cache_dir))
			fandom_checks[page] = check
		if check.status != "missing-page":
			return check
	return FandomCheck(page=", ".join(pages), status="missing-page", issue_numbers=())


def fetch_fandom_check(page: str, delay_seconds: float, cache_dir: Path) -> FandomCheck:
	cache_path = cache_file_for_page(cache_dir, page)
	if cache_path.is_file():
		payload = json.loads(cache_path.read_text(encoding="utf-8"))
		return FandomCheck(
			page=payload["page"],
			status=payload["status"],
			issue_numbers=tuple(payload.get("issue_numbers") or ()),
			error=payload.get("error", ""),
		)
	try:
		issues = fetch_fandom_issues(page, delay_seconds, None)
	except Exception as exc:
		error = str(exc)
		status = "missing-page" if "missingtitle" in error.lower() or "does not exist" in error.lower() else "error"
		check = FandomCheck(page=page, status=status, issue_numbers=(), error=error)
	else:
		check = FandomCheck(
			page=page,
			status="ok",
			issue_numbers=tuple(issue.issue_number for issue in issues),
		)
	cache_path.parent.mkdir(parents=True, exist_ok=True)
	cache_path.write_text(
		json.dumps(
			{
				"page": check.page,
				"status": check.status,
				"issue_numbers": list(check.issue_numbers),
				"error": check.error,
			},
			indent="\t",
		),
		encoding="utf-8",
	)
	return check


def cache_file_for_page(cache_dir: Path, page: str) -> Path:
	if not cache_dir.is_absolute():
		cache_dir = project_root() / cache_dir
	slug = re.sub(r"[^A-Za-z0-9]+", "-", page).strip("-").lower() or "unknown"
	digest = hashlib.sha1(page.encode("utf-8")).hexdigest()[:12]
	return cache_dir / f"{slug}-{digest}.json"


def fandom_page_candidates(run: RunRow, *, infer: bool) -> list[str]:
	pages = []
	pages.extend(fandom_pages_from_notes(run.notes))
	if not infer:
		return dedupe(pages)
	base_title = normalize_fandom_title(run.title)
	without_article = normalize_fandom_title(remove_leading_article(run.title))
	for title in [base_title, without_article]:
		if not title:
			continue
		if run.volume:
			pages.append(f"{title}_Vol_{run.volume}")
		pages.append(title)
	return dedupe(pages)


def fandom_pages_from_notes(notes: str) -> list[str]:
	pages: list[str] = []
	for match in re.finditer(r"Marvel Fandom page\s+([^;]+)", notes):
		pages.extend(volume_first_fandom_pages(match.group(1)))
	for match in re.finditer(r"https://marvel\.fandom\.com/wiki/([^\s)]+)", notes):
		pages.extend(volume_first_fandom_pages(urllib.parse.unquote(match.group(1))))
	return pages


def volume_first_fandom_pages(raw_page: str) -> list[str]:
	page = normalize_fandom_title(raw_page).strip().rstrip(".")
	match = re.match(r"^(.+_Vol_\d+)_[-A-Za-z0-9.]+$", page)
	if match:
		return [match.group(1), page]
	return [page]


def append_watchlist(lines: list[str], runs: list[RunRow]) -> None:
	lines.extend(["## Annual/Special/Giant/Event Watchlist", ""])
	watch_rows = [
		run
		for run in runs
		if any(re.search(pattern, f"{run.title} {run.publication_type}", re.I) for pattern in WATCH_PATTERNS)
	]
	if not watch_rows:
		lines.extend(["No watchlist rows found.", ""])
		return
	for run in watch_rows:
		count_note = (
			f"DB {len(run.db_issue_numbers)} / Marvel {run.marvel_issue_count}"
			if run.marvel_issue_count is not None
			else f"DB {len(run.db_issue_numbers)} / Marvel count unknown"
		)
		lines.append(
			f"- `{run.priority}` `{run.id}` {run.title} vol. {run.volume or '?'} ({run.years or '?'}) "
			f"[{run.publication_type or 'unknown'}]: {count_note}"
		)
	lines.append("")


def append_negative_issues(lines: list[str], runs: list[RunRow]) -> None:
	lines.extend(["## Negative Issue Rows", ""])
	negative_rows = [
		(run, sorted_issue_numbers(number for number in run.db_issue_numbers if number.startswith("-")))
		for run in runs
	]
	negative_rows = [(run, issue_numbers) for run, issue_numbers in negative_rows if issue_numbers]
	if not negative_rows:
		lines.extend(["No negative-numbered issue rows found.", ""])
		return
	for run, issue_numbers in negative_rows:
		lines.append(
			f"- `{run.priority}` `{run.id}` {run.title} vol. {run.volume or '?'} "
			f"({run.years or '?'}): {', '.join(issue_numbers)}"
		)
	lines.append("")


def append_missing_marvel_series(
	lines: list[str],
	runs: list[RunRow],
	delay_seconds: float,
) -> None:
	lines.extend(["## Marvel Series Discovery Gaps", ""])
	known_keys = known_series_keys(runs)
	candidates = [
		series
		for series in fetch_marvel_series_index(delay_seconds)
		if is_in_scope_series(series.name)
		and f"marvel:{series.id}" not in known_keys
		and normalize_series_name(series.name) not in known_keys
	]
	if not candidates:
		lines.extend(["No missing Marvel metadata series candidates found.", ""])
		return
	for series in sorted(candidates, key=lambda item: (inferred_priority(item.name), item.name.casefold())):
		lines.append(
			f"- `{inferred_priority(series.name)}` Marvel series `{series.id}`: {series.name} "
			f"(issueCount={series.issue_count})"
		)
	lines.append("")


def fetch_marvel_series_index(delay_seconds: float) -> list[MarvelSeries]:
	offset = 0
	series: list[MarvelSeries] = []
	while True:
		url = f"{MARVEL_METADATA_API}/series?limit=200&offset={offset}"
		payload = fetch_json(url)
		for item in payload.get("items", []):
			series.append(
				MarvelSeries(
					id=int(item["id"]),
					name=str(item.get("name") or ""),
					issue_count=item.get("issueCount"),
				)
			)
		if not payload.get("has_next"):
			break
		offset += int(payload.get("limit") or 200)
		time.sleep(delay_seconds)
	return series


def fetch_json(url: str) -> dict[str, Any]:
	request = urllib.request.Request(
		url,
		headers={"Accept": "application/json", "User-Agent": "ComicOrganizer/0.1"},
	)
	with urllib.request.urlopen(request, timeout=30) as response:
		return json.loads(response.read().decode("utf-8"))


def known_series_keys(runs: list[RunRow]) -> set[str]:
	keys = {normalize_series_name(f"{run.title} ({run.years})") for run in runs if run.years}
	keys.update(normalize_series_name(run.title) for run in runs)
	for run in runs:
		match = re.search(r"/series/(\d+)", run.marvel_url)
		if match:
			keys.add(f"marvel:{match.group(1)}")
	return keys


def is_in_scope_series(name: str) -> bool:
	text = name.casefold()
	if not any(re.search(pattern, text, re.I) for pattern in INCLUDE_PATTERNS):
		return False
	if any(re.search(pattern, text, re.I) for pattern in EXCLUDE_PATTERNS):
		return False
	return True


def inferred_priority(name: str) -> str:
	text = name.casefold()
	if "amazing spider-man" in text or "spectacular spider-man" in text or "ultimate spider-man" in text:
		return "P0"
	if "miles morales" in text or "spider-gwen" in text or "venom" in text or "spider-verse" in text:
		return "P1"
	return "P2"


def normalize_series_name(value: str) -> str:
	text = value.casefold()
	text = re.sub(r"\bthe\b", "", text)
	text = re.sub(r"\bpresent\b", "", text)
	text = re.sub(r"[^a-z0-9]+", " ", text)
	return re.sub(r"\s+", " ", text).strip()


def normalize_fandom_title(value: str) -> str:
	return re.sub(r"\s+", "_", value.strip())


def remove_leading_article(value: str) -> str:
	return re.sub(r"^The\s+", "", value.strip(), flags=re.I)


def sorted_issue_numbers(values: frozenset[str]) -> list[str]:
	return sorted(values, key=issue_sort_key)


def issue_sort_key(value: str) -> tuple[float, str]:
	match = re.match(r"^-?\d+(?:\.\d+)?", value)
	number = float(match.group(0)) if match else 0
	return number, value.casefold()


def ellipsis(values: list[str], limit: int) -> str:
	return f" ... (+{len(values) - limit} more)" if len(values) > limit else ""


def dedupe(values: list[str]) -> list[str]:
	seen: set[str] = set()
	deduped: list[str] = []
	for value in values:
		if not value or value in seen:
			continue
		seen.add(value)
		deduped.append(value)
	return deduped


if __name__ == "__main__":
	raise SystemExit(main())
