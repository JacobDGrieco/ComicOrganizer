"""Backfill issue story arcs and within-arc order from Marvel Fandom pages."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from db_common import connect_database, project_root

FANDOM_API_URL = "https://marvel.fandom.com/api.php"
DAY_PRECISION_FORMATS = ("%B %d, %Y", "%b %d, %Y")
MONTH_PRECISION_FORMATS = ("%B %Y", "%b %Y")


class FandomPageMissing(RuntimeError):
	pass


@dataclass(frozen=True)
class IssueRow:
	id: str
	cand_id: str
	run_title: str
	volume: str
	issue_number: str
	release_date: str
	release_date_precision: str
	story_arc_id: str
	sort_order: int | None
	notes: str


@dataclass(frozen=True)
class FandomPage:
	requested_page: str
	title: str
	wikitext: str


@dataclass(frozen=True)
class ArcCandidate:
	page: str
	title: str
	source_kind: str


@dataclass(frozen=True)
class ArcMetadata:
	id: str
	page: str
	title: str
	start_date: str
	start_date_precision: str
	end_date: str | None
	end_date_precision: str
	order_map: dict[str, int]


@dataclass(frozen=True)
class BackfillDecision:
	issue: IssueRow
	issue_page: str
	arc: ArcMetadata
	sort_order: int | None


def main() -> int:
	args = parse_args()
	cache_dir = Path(args.cache_dir)
	if not cache_dir.is_absolute():
		cache_dir = project_root() / cache_dir
	cache_dir.mkdir(parents=True, exist_ok=True)

	with connect_database(args.db) as connection:
		ensure_sort_order_schema(connection, dry_run=args.dry_run)
		issues = fetch_issue_rows(connection, args)
		local_dates = build_local_date_index(issues)

	fandom_client = FandomClient(cache_dir, args.delay_seconds)
	arc_cache: dict[str, ArcMetadata] = {}
	decisions: list[BackfillDecision] = []
	missing_pages = 0
	without_arc = 0
	applied = 0

	write_connection = None if args.dry_run else connect_database(args.db)
	try:
		if write_connection is not None:
			ensure_sort_order_schema(write_connection, dry_run=False)
		for index, issue in enumerate(issues, start=1):
			try:
				issue_page = fandom_client.first_existing_page(issue_page_candidates(issue))
				page = fandom_client.fetch_page(issue_page)
			except FandomPageMissing:
				missing_pages += 1
				continue

			candidates = parse_issue_arc_candidates(page.wikitext)
			if not candidates:
				without_arc += 1
				continue

			arc = select_earliest_arc(
				candidates,
				fandom_client,
				arc_cache,
				local_dates,
				issue,
			)
			sort_order = arc.order_map.get(normalize_page_key(issue_page))
			decision = BackfillDecision(issue, issue_page, arc, sort_order)
			decisions.append(decision)
			if write_connection is not None:
				apply_decision(write_connection, decision)
				applied += 1
				if applied % args.commit_interval == 0:
					write_connection.commit()
			if args.progress_interval and index % args.progress_interval == 0:
				print(
					f"Inspected {index}/{len(issues)} issues; "
					f"resolved={len(decisions)} ordered={sum(1 for item in decisions if item.sort_order is not None)} "
					f"missing_pages={missing_pages} without_arc={without_arc}",
					flush=True,
				)
		if write_connection is not None:
			write_connection.commit()
	finally:
		if write_connection is not None:
			write_connection.close()

	if args.dry_run:
		print_summary(args, decisions, missing_pages, without_arc, dry_run=True)
		return 0

	print_summary(args, decisions, missing_pages, without_arc, dry_run=False)
	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Backfill SQLite issue story arcs from Marvel Fandom issue pages."
	)
	parser.add_argument("--db", default="database/database.db", help="SQLite database path.")
	parser.add_argument(
		"--cache-dir",
		default=".cache/fandom-story-arcs",
		help="Directory for cached Fandom API responses.",
	)
	parser.add_argument("--run-id", help="Only process one comic_runs.id value.")
	parser.add_argument("--issue-id", help="Only process one issues.id value.")
	parser.add_argument("--priority", help="Only process runs with this comic_runs.priority value.")
	parser.add_argument("--limit", type=int, help="Maximum issue rows to inspect.")
	parser.add_argument("--offset", type=int, default=0, help="Issue-row offset for chunked sweeps.")
	parser.add_argument(
		"--only-missing",
		action="store_true",
		help="Only process rows without a resolved Fandom story arc and without sort_order.",
	)
	parser.add_argument(
		"--delay-seconds",
		type=float,
		default=0.15,
		help="Delay before uncached Fandom requests.",
	)
	parser.add_argument(
		"--commit-interval",
		type=int,
		default=50,
		help="Commit after this many applied updates. Defaults to 50.",
	)
	parser.add_argument(
		"--progress-interval",
		type=int,
		default=100,
		help="Print progress after this many inspected issues. Defaults to 100.",
	)
	parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
	return parser.parse_args()


def ensure_sort_order_schema(connection, *, dry_run: bool) -> None:
	columns = {
		row["name"]
		for row in connection.execute("PRAGMA table_info(issues)").fetchall()
	}
	if "sort_order" not in columns and not dry_run:
		connection.execute("ALTER TABLE issues ADD COLUMN sort_order INTEGER")
	if not dry_run:
		connection.execute(
			"""
			CREATE INDEX IF NOT EXISTS idx_issues_story_arc_sort_order
			ON issues(story_arc_id, sort_order, release_date)
			"""
		)


def fetch_issue_rows(connection, args: argparse.Namespace) -> list[IssueRow]:
	conditions: list[str] = []
	parameters: list[str | int] = []
	has_sort_order = column_exists(connection, "issues", "sort_order")
	sort_order_expression = "issues.sort_order" if has_sort_order else "NULL"
	if args.run_id:
		conditions.append("comic_runs.id = ?")
		parameters.append(args.run_id)
	if args.issue_id:
		conditions.append("issues.id = ?")
		parameters.append(args.issue_id)
	if args.priority:
		conditions.append("comic_runs.priority = ?")
		parameters.append(args.priority)
	if args.only_missing:
		if has_sort_order:
			conditions.append("issues.sort_order IS NULL")
		conditions.append("issues.story_arc_id NOT LIKE 'FANDOM-EVENT-%'")
		conditions.append("issues.story_arc_id NOT LIKE 'FANDOM-STORY-%'")
	where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
	limit_clause = "LIMIT ?" if args.limit else ""
	offset_clause = "OFFSET ?" if args.limit and args.offset else ""
	if args.limit:
		parameters.append(args.limit)
		if args.offset:
			parameters.append(args.offset)
	rows = connection.execute(
		f"""
		SELECT
			issues.id,
			issues.cand_id,
			comic_runs.title AS run_title,
			comic_runs.volume,
			issues.issue_number,
			issues.release_date,
			issues.release_date_precision,
			issues.story_arc_id,
			{sort_order_expression} AS sort_order,
			COALESCE(comic_runs.notes, '') AS notes
		FROM issues
		JOIN comic_runs ON comic_runs.id = issues.cand_id
		{where_clause}
		ORDER BY issues.release_date, comic_runs.title, CAST(issues.issue_number AS REAL), issues.issue_number
		{limit_clause}
		{offset_clause}
		""",
		parameters,
	).fetchall()
	return [
		IssueRow(
			id=row["id"],
			cand_id=row["cand_id"],
			run_title=row["run_title"],
			volume=str(row["volume"] or ""),
			issue_number=str(row["issue_number"]),
			release_date=row["release_date"],
			release_date_precision=row["release_date_precision"],
			story_arc_id=row["story_arc_id"],
			sort_order=row["sort_order"],
			notes=row["notes"],
		)
		for row in rows
	]


def column_exists(connection, table_name: str, column_name: str) -> bool:
	return any(
		row["name"] == column_name
		for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
	)


def build_local_date_index(issues: list[IssueRow]) -> dict[str, tuple[str, str]]:
	local_dates: dict[str, tuple[str, str]] = {}
	for issue in issues:
		for page in issue_page_candidates(issue):
			local_dates.setdefault(
				normalize_page_key(page),
				(issue.release_date, issue.release_date_precision),
			)
	return local_dates


class FandomClient:
	def __init__(self, cache_dir: Path, delay_seconds: float) -> None:
		self.cache_dir = cache_dir
		self.delay_seconds = delay_seconds
		self.memory_cache: dict[str, FandomPage] = {}

	def first_existing_page(self, pages: list[str]) -> str:
		last_error: FandomPageMissing | None = None
		for page in pages:
			try:
				return self.fetch_page(page).title
			except FandomPageMissing as exc:
				last_error = exc
		raise last_error or FandomPageMissing("No candidate pages supplied.")

	def fetch_page(self, page: str) -> FandomPage:
		page = normalize_page_title(page)
		key = normalize_page_key(page)
		if key in self.memory_cache:
			return self.memory_cache[key]

		cache_file = self.cache_dir / f"{slugify(key)}.json"
		if cache_file.exists():
			payload = json.loads(cache_file.read_text(encoding="utf-8"))
			fandom_page = FandomPage(
				requested_page=page,
				title=payload["title"],
				wikitext=payload["wikitext"],
			)
			self.memory_cache[key] = fandom_page
			return fandom_page

		query = urllib.parse.urlencode(
			{
				"action": "parse",
				"page": page,
				"prop": "wikitext",
				"format": "json",
			}
		)
		request = urllib.request.Request(
			f"{FANDOM_API_URL}?{query}",
			headers={"Accept": "application/json", "User-Agent": "ComicOrganizer/0.1"},
		)
		payload = None
		for attempt in range(3):
			time.sleep(self.delay_seconds if attempt == 0 else max(1.0, self.delay_seconds) * attempt)
			try:
				with urllib.request.urlopen(request, timeout=30) as response:
					payload = json.loads(response.read().decode("utf-8"))
				break
			except urllib.error.HTTPError as exc:
				if exc.code == 404:
					raise FandomPageMissing(page) from exc
				if exc.code not in {429, 500, 502, 503, 504, 520, 521, 522, 523, 524}:
					raise
			except urllib.error.URLError:
				pass
		if payload is None:
			raise FandomPageMissing(page)
		if "error" in payload:
			raise FandomPageMissing(page)

		parsed = payload.get("parse") or {}
		fandom_page = FandomPage(
			requested_page=page,
			title=str(parsed.get("title") or page),
			wikitext=str((parsed.get("wikitext") or {}).get("*") or ""),
		)
		cache_file.write_text(
			json.dumps(
				{"title": fandom_page.title, "wikitext": fandom_page.wikitext},
				ensure_ascii=True,
				indent=2,
			),
			encoding="utf-8",
		)
		self.memory_cache[key] = fandom_page
		self.memory_cache[normalize_page_key(fandom_page.title)] = fandom_page
		return fandom_page


def issue_page_candidates(issue: IssueRow) -> list[str]:
	pages: list[str] = []
	source_volume_page = run_fandom_volume_page(issue)
	if source_volume_page:
		pages.append(f"{source_volume_page}_{issue.issue_number}")

	base_titles = [
		issue.run_title,
		remove_leading_article(issue.run_title),
		issue.run_title.replace(", the ", ", The "),
	]
	for title in base_titles:
		page = f"{normalize_page_title(title)}_Vol_{issue.volume}_{issue.issue_number}"
		if page not in pages:
			pages.append(page)
	return pages


def run_fandom_volume_page(issue: IssueRow) -> str | None:
	match = re.search(r"Marvel Fandom page ([^;]+)", issue.notes)
	if match:
		return normalize_page_title(match.group(1).strip().rstrip("."))
	return None


def parse_issue_arc_candidates(wikitext: str) -> list[ArcCandidate]:
	event_candidates = parse_numbered_page_fields(wikitext, "Event", "event")
	if event_candidates:
		return event_candidates
	return parse_numbered_page_fields(wikitext, "StoryArc", "story")


def parse_numbered_page_fields(wikitext: str, field_name: str, source_kind: str) -> list[ArcCandidate]:
	candidates: list[ArcCandidate] = []
	for match in re.finditer(
		rf"(?m)^\|[ \t]*{re.escape(field_name)}(\d*)[ \t]*=[ \t]*(.*?)[ \t]*$",
		wikitext,
	):
		raw_value = match.group(2).strip()
		if not raw_value:
			continue
		page, title = page_reference_from_value(raw_value)
		if not page:
			continue
		candidate = ArcCandidate(page=page, title=title or page.replace("_", " "), source_kind=source_kind)
		if normalize_page_key(candidate.page) not in {normalize_page_key(existing.page) for existing in candidates}:
			candidates.append(candidate)
	return candidates


def page_reference_from_value(raw_value: str) -> tuple[str | None, str]:
	value = raw_value.strip()
	template_match = re.search(r"\{\{(?:cl|sl)\|([^}|]+)(?:\|([^}]+))?\}\}", value, re.I)
	if template_match:
		page = template_match.group(1).strip()
		title = strip_wiki_markup(template_match.group(2) or page)
		return normalize_page_title(page), title
	link_match = re.search(r"\[\[([^]|#]+)(?:#[^]|]+)?(?:\|([^]]+))?\]\]", value)
	if link_match:
		page = link_match.group(1).strip()
		title = strip_wiki_markup(link_match.group(2) or page)
		return normalize_page_title(page), title
	title = strip_wiki_markup(value)
	title = re.sub(r"\s+", " ", title).strip()
	return (normalize_page_title(title), title) if title else (None, "")


def select_earliest_arc(
	candidates: list[ArcCandidate],
	fandom_client: FandomClient,
	arc_cache: dict[str, ArcMetadata],
	local_dates: dict[str, tuple[str, str]],
	issue: IssueRow,
) -> ArcMetadata:
	metadata = [
		arc_metadata(candidate, fandom_client, arc_cache, local_dates, issue)
		for candidate in candidates
	]
	return min(metadata, key=lambda arc: date_sort_key(arc.start_date))


def arc_metadata(
	candidate: ArcCandidate,
	fandom_client: FandomClient,
	arc_cache: dict[str, ArcMetadata],
	local_dates: dict[str, tuple[str, str]],
	issue: IssueRow,
) -> ArcMetadata:
	key = normalize_page_key(candidate.page)
	if key in arc_cache:
		return arc_cache[key]
	try:
		page = fandom_client.fetch_page(candidate.page)
		wikitext = page.wikitext
		page_title = page.title
	except FandomPageMissing:
		wikitext = ""
		page_title = candidate.title

	order_pages = ordered_arc_issue_pages(wikitext)
	order_map = {
		normalize_page_key(page_name): position
		for position, page_name in enumerate(order_pages, start=1)
	}
	dates = ordered_known_dates(order_pages, local_dates)
	if not dates and order_pages:
		first_date = fetch_issue_release_date(order_pages[0], fandom_client)
		if first_date is not None:
			dates.append(first_date)
	if dates:
		start_date, start_precision = min(dates, key=lambda row: date_sort_key(row[0]))
		end_date, end_precision = max(dates, key=lambda row: date_sort_key(row[0]))
	else:
		start_date = issue.release_date
		start_precision = issue.release_date_precision
		end_date = issue.release_date
		end_precision = issue.release_date_precision

	arc_prefix = "FANDOM-EVENT" if candidate.source_kind == "event" else "FANDOM-STORY"
	metadata = ArcMetadata(
		id=f"{arc_prefix}-{slugify(page_title)}",
		page=page_title,
		title=page_title.replace("_", " "),
		start_date=start_date,
		start_date_precision=start_precision,
		end_date=end_date,
		end_date_precision=end_precision,
		order_map=order_map,
	)
	arc_cache[key] = metadata
	arc_cache[normalize_page_key(page_title)] = metadata
	return metadata


def ordered_arc_issue_pages(wikitext: str) -> list[str]:
	reading_order_pages = extract_reading_order_pages(wikitext)
	if reading_order_pages:
		return reading_order_pages

	part_pages = [
		(int(match.group(1)), normalize_page_title(match.group(2)))
		for match in re.finditer(r"(?m)^\|[ \t]*Part(\d+)[ \t]*=[ \t]*(.*?)[ \t]*$", wikitext)
		if match.group(2).strip()
	]
	if part_pages:
		return dedupe_pages([page for _, page in sorted(part_pages)])

	return extract_tie_in_pages(wikitext)


def extract_reading_order_pages(wikitext: str) -> list[str]:
	pages: list[str] = []
	is_reading_order = False
	for line in wikitext.splitlines():
		if "Reading Order" in line:
			is_reading_order = True
			continue
		if not is_reading_order:
			continue
		if not line.strip():
			is_reading_order = False
			continue
		if line.startswith("| ") or re.match(r"^={2,}", line):
			is_reading_order = False
			continue
		if line.lstrip().startswith("*"):
			pages.extend(extract_issue_references(line))
	return dedupe_pages(pages)


def extract_tie_in_pages(wikitext: str) -> list[str]:
	pages: list[str] = []
	is_tie_in_block = False
	for line in wikitext.splitlines():
		if re.match(r"^\|\s*TieIns\s*=", line):
			is_tie_in_block = True
		elif is_tie_in_block and re.match(r"^\|\s*[A-Za-z0-9_]+\s*=", line):
			break
		if is_tie_in_block:
			pages.extend(extract_issue_references(line))
	return dedupe_pages(pages)


def extract_issue_references(line: str) -> list[str]:
	references: list[str] = []
	for match in re.finditer(r"\{\{(?:cl|sl)\|([^}|]+)(?:\|[^}]+)?\}\}", line, re.I):
		references.append(normalize_page_title(match.group(1)))
	for match in re.finditer(r"\[\[([^]|#]+)(?:#[^]|]+)?(?:\|[^]]+)?\]\]", line):
		references.append(normalize_page_title(match.group(1)))
	expanded = expand_issue_range(references)
	return expanded or references


def expand_issue_range(references: list[str]) -> list[str]:
	if len(references) != 2:
		return []
	start = parse_issue_page_reference(references[0])
	end = parse_issue_page_reference(references[1])
	if start is None or end is None:
		return []
	start_base, start_number = start
	end_base, end_number = end
	if start_base != end_base or start_number >= end_number:
		return []
	return [f"{start_base}_{number}" for number in range(start_number, end_number + 1)]


def parse_issue_page_reference(page: str) -> tuple[str, int] | None:
	match = re.match(r"^(?P<base>.+_Vol_\d+)_(?P<number>\d+)$", normalize_page_title(page))
	if not match:
		return None
	return match.group("base"), int(match.group("number"))


def ordered_known_dates(
	order_pages: list[str], local_dates: dict[str, tuple[str, str]]
) -> list[tuple[str, str]]:
	dates: list[tuple[str, str]] = []
	for page in order_pages:
		local_date = local_dates.get(normalize_page_key(page))
		if local_date is not None:
			dates.append(local_date)
	return dates


def fetch_issue_release_date(page: str, fandom_client: FandomClient) -> tuple[str, str] | None:
	try:
		fandom_page = fandom_client.fetch_page(page)
	except FandomPageMissing:
		return None
	for field_name in ("ReleaseDate", "Year"):
		release_date, precision = parse_fandom_date(template_field(fandom_page.wikitext, field_name))
		if release_date is not None:
			return release_date, precision
	return None


def apply_decision(connection, decision: BackfillDecision) -> None:
	upsert_arc(connection, decision.arc)
	connection.execute(
		"""
		UPDATE issues
		SET story_arc_id = ?, sort_order = ?
		WHERE id = ?
		""",
		(decision.arc.id, decision.sort_order, decision.issue.id),
	)


def upsert_arc(connection, arc: ArcMetadata) -> None:
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
			arc.id,
			arc.title,
			arc.start_date,
			arc.start_date_precision,
			arc.end_date,
			arc.end_date_precision,
		),
	)


def template_field(wikitext: str, field_name: str) -> str:
	match = re.search(rf"(?m)^\|[ \t]*{re.escape(field_name)}[ \t]*=[ \t]*(.*?)[ \t]*$", wikitext)
	return match.group(1).strip() if match else ""


def parse_fandom_date(raw_date: str) -> tuple[str | None, str]:
	text = strip_wiki_markup(raw_date).strip()
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
	if re.match(r"^\d{4}$", text):
		return text, "year"
	return None, "unknown"


def strip_wiki_markup(value: str) -> str:
	text = re.sub(r"<[^>]+>", "", value)
	text = re.sub(r"''+", "", text)
	text = re.sub(r"\{\{[^{}]+\}\}", "", text)
	text = text.replace("[[", "").replace("]]", "")
	if "|" in text:
		text = text.split("|")[-1]
	return text.strip()


def normalize_page_title(value: str) -> str:
	return re.sub(r"\s+", "_", value.strip()).replace(" ", "_")


def normalize_page_key(value: str) -> str:
	return urllib.parse.unquote(normalize_page_title(value)).replace("_", " ").casefold()


def remove_leading_article(value: str) -> str:
	return re.sub(r"^The\s+", "", value.strip(), flags=re.I)


def date_sort_key(value: str) -> str:
	if re.match(r"^\d{4}$", value):
		return f"{value}-99-99"
	if re.match(r"^\d{4}-\d{2}$", value):
		return f"{value}-99"
	return value


def dedupe_pages(pages: list[str]) -> list[str]:
	seen: set[str] = set()
	deduped: list[str] = []
	for page in pages:
		key = normalize_page_key(page)
		if not page or key in seen:
			continue
		seen.add(key)
		deduped.append(page)
	return deduped


def slugify(value: str) -> str:
	slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
	return slug or "UNKNOWN"


def print_summary(
	args: argparse.Namespace,
	decisions: list[BackfillDecision],
	missing_pages: int,
	without_arc: int,
	*,
	dry_run: bool,
) -> None:
	mode = "Dry run" if dry_run else "Backfill"
	ordered = sum(1 for decision in decisions if decision.sort_order is not None)
	print(
		f"{mode}: inspected limit={args.limit or 'all'} "
		f"offset={args.offset or 0} priority={args.priority or 'all'}"
	)
	print(f"Resolved story arcs: {len(decisions)}")
	print(f"Resolved sort_order values: {ordered}")
	print(f"Missing issue pages: {missing_pages}")
	print(f"Issue pages without Event/StoryArc fields: {without_arc}")
	for decision in decisions[:20]:
		order = decision.sort_order if decision.sort_order is not None else "release-date fallback"
		print(
			f"{decision.issue.id}: {decision.issue_page} -> {decision.arc.title} "
			f"({decision.arc.start_date}), sort_order={order}"
		)


if __name__ == "__main__":
	raise SystemExit(main())
