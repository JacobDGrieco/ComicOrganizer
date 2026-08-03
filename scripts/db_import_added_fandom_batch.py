"""Batch-import Fandom issue rows for recently added comic-run candidates."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from types import SimpleNamespace

from db_common import connect_database
from db_import_fandom_volume import (
	FandomIssue,
	append_import_note,
	fetch_fandom_issues,
	fetch_run_scope,
	filter_issues_by_max_release_date,
	filter_issues_by_scope,
	normalize_issue_number,
	upsert_issue,
)


@dataclass(frozen=True)
class ImportResult:
	run_id: str
	title: str
	status: str
	page: str
	imported_count: int
	expected_count: int | None
	message: str


MANUAL_ISSUE_PAGES: dict[str, list[tuple[str, str]]] = {
	"CAND-000401": [("Marvel_Graphic_Novel_Vol_1_22:_The_Amazing_Spider-Man:_Hooky", "22")],
	"CAND-000402": [("Marvel_Graphic_Novel_Vol_1_46:_The_Amazing_Spider-Man:_Parallel_Lives", "46")],
	"CAND-000403": [("Marvel_Graphic_Novel_Vol_1_63:_Spider-Man:_Spirits_of_the_Earth", "63")],
	"CAND-000404": [("Marvel_Graphic_Novel_Vol_1_72:_Spider-Man:_Fear_Itself", "72")],
	"CAND-000449": [("Marvel_Spotlight_Vol_1_32", "32")],
	"CAND-000471": [("What_If...?_Vol_1_105", "105")],
	"CAND-000580": [(f"Mystic_Comics_Vol_1_{issue}", str(issue)) for issue in range(1, 5)],
	"CAND-000482": [(f"Spider-Man_Unlimited_Infinity_Comic_Vol_1_{issue}", str(issue)) for issue in range(1, 13)],
}


FANDOM_PAGE_OVERRIDES: dict[str, list[str]] = {
	"CAND-000247": ["Marvel_Universe_Ultimate_Spider-Man:_Web_Warriors_-_Spider-Verse_Vol_1"],
	"CAND-000284": ["Marvel_Universe_Ultimate_Spider-Man:_Web_Warriors_-_Contest_of_Champions_Vol_1"],
	"CAND-000601": ["Marvel_Universe_Ultimate_Spider-Man_vs._the_Sinister_Six_Vol_1"],
	"CAND-000612": ["Marvel_Universe_Ultimate_Spider-Man:_Web_Warriors_Vol_1", "Ultimate_Spider-Man:_Web_Warriors_Vol_1"],
	"CAND-000614": ["Clone_Conspiracy_Omega_Vol_1", "The_Clone_Conspiracy:_Omega_Vol_1"],
	"CAND-000619": ["Dark_Web_Finale_Vol_1"],
	"CAND-000622": ["Dark_Reign:_Mister_Negative_Vol_1"],
	"CAND-000389": ["Spidey/Marrow_Vol_1"],
	"CAND-000390": ["Spider-Man_vs_Punisher_Vol_1"],
	"CAND-000411": ["Spider-Man/Gen¹³_Vol_1"],
	"CAND-000401": ["Amazing_Spider-Man:_Hooky_Vol_1"],
	"CAND-000402": ["Amazing_Spider-Man:_Parallel_Lives_Vol_1"],
	"CAND-000403": ["Spider-Man:_Spirits_of_the_Earth_Vol_1"],
	"CAND-000404": ["Spider-Man:_Fear_Itself_Vol_1"],
	"CAND-000507": ["Venom:_Enemy_Within_Vol_1"],
	"CAND-000534": ["Web_of_Venom:_Ve'Nam_Vol_1"],
	"CAND-000536": ["Web_of_Venom:_Unleashed_Vol_1"],
	"CAND-000537": ["Web_of_Venom:_Cult_of_Carnage_Vol_1"],
	"CAND-000538": ["Web_of_Venom:_Funeral_Pyre_Vol_1"],
	"CAND-000541": ["Web_of_Venom:_Empyre's_End_Vol_1"],
	"CAND-000542": ["King_in_Black:_Black_Knight_Vol_1"],
	"CAND-000543": ["King_in_Black:_Black_Panther_Vol_1"],
	"CAND-000552": ["King_in_Black:_Scream_Vol_1"],
	"CAND-000545": ["King_in_Black:_Ghost_Rider_Vol_1"],
	"CAND-000546": ["King_in_Black:_Immortal_Hulk_Vol_1"],
	"CAND-000547": ["King_in_Black:_Iron_Man/Doom_Vol_1"],
	"CAND-000548": ["King_in_Black:_Marauders_Vol_1"],
	"CAND-000558": ["Ruins_of_Ravencroft:_Carnage_Vol_1"],
	"CAND-000579": ["Guardians_of_the_Galaxy_Annual_Vol_2"],
	"CAND-000596": ["How_to_Read_Comics_the_Marvel_Way_Vol_1"],
	"CAND-000606": ["Who_Is..._Kingpin_Infinity_Comic_Vol_1"],
	"CAND-000608": ["Who_Is..._Kraven_Infinity_Comic_Vol_1"],
	"CAND-000609": ["Mighty_Marvel_Holiday_Special_â€“_Halloween_with_the_Rhino_Infinity_Comic_Vol_1"],
}


EXPECTED_COUNT_OVERRIDES: dict[str, int] = {
	"CAND-000383": 7,
}


SKIP_NOTE_PATTERNS = (
	"import only in-scope",
	"import only spider",
	"import only agent",
	"import only flash",
	"verify scope",
	"verify issue-level relevance",
	"verify spider-ham entry scope",
	"only spider-family",
	"only spider-girl",
	"only flexo",
	"only #",
	"avoid reprint-only",
)


def main() -> int:
	args = parse_args()
	with connect_database(args.db) as connection:
		runs = fetch_runs(connection, args)

	results: list[ImportResult] = []
	for run in runs:
		result = import_run(args, run)
		results.append(result)
		print_result(result)
		if args.stop_on_error and result.status == "error":
			break

	print_summary(results)
	return 1 if any(result.status == "error" for result in results) else 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Batch-import recently added Marvel Fandom issue rows."
	)
	parser.add_argument("--db", default="projects/spider-man/database/database.db", help="SQLite database path.")
	parser.add_argument("--min-run-id", default="CAND-000323", help="First comic_runs.id to consider.")
	parser.add_argument("--max-run-id", help="Last comic_runs.id to consider.")
	parser.add_argument("--run-id", action="append", help="Specific comic_runs.id to import. May be repeated.")
	parser.add_argument("--delay-seconds", type=float, default=0.25, help="Delay between Fandom requests.")
	parser.add_argument("--max-release-date", default="2026-08-01", help="Do not import future-dated issues.")
	parser.add_argument("--refresh-existing", action="store_true", help="Refresh existing release dates.")
	parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
	parser.add_argument("--stop-on-error", action="store_true", help="Stop after the first failed import.")
	return parser.parse_args()


def fetch_runs(connection, args: argparse.Namespace) -> list[dict[str, object]]:
	conditions = ["comic_runs.id >= ?"]
	parameters: list[object] = [args.min_run_id]
	if args.max_run_id:
		conditions.append("comic_runs.id <= ?")
		parameters.append(args.max_run_id)
	if args.run_id:
		placeholders = ",".join("?" for _ in args.run_id)
		conditions.append(f"comic_runs.id IN ({placeholders})")
		parameters.extend(args.run_id)
	where_clause = " AND ".join(conditions)
	rows = connection.execute(
		f"""
		SELECT
			comic_runs.id,
			comic_runs.title,
			COALESCE(comic_runs.volume, '') AS volume,
			COALESCE(comic_runs.years, '') AS years,
			COALESCE(comic_runs.publication_type, '') AS publication_type,
			comic_runs.marvel_issue_count,
			COALESCE(comic_runs.notes, '') AS notes,
			COUNT(issues.id) AS issue_rows
		FROM comic_runs
		LEFT JOIN issues ON issues.cand_id = comic_runs.id
		WHERE {where_clause}
		GROUP BY comic_runs.id
		ORDER BY comic_runs.id
		""",
		parameters,
	).fetchall()
	return [dict(row) for row in rows]


def import_run(args: argparse.Namespace, run: dict[str, object]) -> ImportResult:
	run_id = str(run["id"])
	title = str(run["title"])
	expected_count = EXPECTED_COUNT_OVERRIDES.get(
		run_id,
		expected_count_as_int(run["marvel_issue_count"]),
	)
	issue_rows = int(run["issue_rows"])
	if expected_count is not None and issue_rows >= expected_count and run_id not in MANUAL_ISSUE_PAGES:
		return ImportResult(run_id, title, "already-complete", "", issue_rows, expected_count, "")
	if should_skip_scoped_run(run) and run_id not in MANUAL_ISSUE_PAGES:
		return ImportResult(run_id, title, "skipped-scoped", "", issue_rows, expected_count, "manual issue scope required")

	try:
		if run_id in MANUAL_ISSUE_PAGES:
			issues = import_manual_issue_pages(args, run_id, MANUAL_ISSUE_PAGES[run_id])
			return ImportResult(run_id, title, "imported" if issues else "no-issues", "manual issue pages", len(issues), len(MANUAL_ISSUE_PAGES[run_id]), "")
		page, issues = fetch_first_matching_page(args, run, expected_count)
		if not issues:
			return ImportResult(run_id, title, "no-issues", page, 0, expected_count, "no dated Fandom issues after filters")
		if not args.dry_run:
			write_issues(args, run_id, page, issues)
		return ImportResult(run_id, title, "imported", page, len(issues), expected_count, "")
	except Exception as exc:  # noqa: BLE001 - batch importer records per-run failures.
		return ImportResult(run_id, title, "error", "", issue_rows, expected_count, str(exc))


def should_skip_scoped_run(run: dict[str, object]) -> bool:
	notes = str(run["notes"]).casefold()
	publication_type = str(run["publication_type"]).casefold()
	if any(pattern in notes for pattern in SKIP_NOTE_PATTERNS):
		return True
	if publication_type in {"anthology", "infinity comic"} and run["id"] not in MANUAL_ISSUE_PAGES:
		return True
	return False


def import_manual_issue_pages(
	args: argparse.Namespace, run_id: str, pages: list[tuple[str, str]]
) -> list[FandomIssue]:
	imported: list[FandomIssue] = []
	for page, issue_number in pages:
		issues = fetch_fandom_issues(page, args.delay_seconds, issue_number)
		issues = filter_issues_by_max_release_date(issues, args.max_release_date)
		if not issues:
			continue
		issue = issues[0]
		imported.append(issue)
		if not args.dry_run:
			write_issues(args, run_id, page, [issue])
	return imported


def fetch_first_matching_page(
	args: argparse.Namespace, run: dict[str, object], expected_count: int | None
) -> tuple[str, list[FandomIssue]]:
	errors: list[str] = []
	for page in fandom_page_candidates(run):
		try:
			with connect_database(args.db) as connection:
				run_scope = fetch_run_scope(connection, str(run["id"]))
			raw_issues = fetch_fandom_issues(page, args.delay_seconds, None)
			issues = filter_issues_by_scope(raw_issues, run_scope, False, 1)
			issues = filter_issues_by_max_release_date(issues, args.max_release_date)
			if expected_count is not None and len(issues) != expected_count:
				errors.append(f"{page}: expected {expected_count}, found {len(issues)}")
				continue
			if issues:
				return page, issues
			errors.append(f"{page}: no dated issues")
		except Exception as exc:  # noqa: BLE001 - candidate probing should continue.
			errors.append(f"{page}: {exc}")
	if expected_count is None:
		for page in fandom_page_candidates(run):
			try:
				with connect_database(args.db) as connection:
					run_scope = fetch_run_scope(connection, str(run["id"]))
				raw_issues = fetch_fandom_issues(page, args.delay_seconds, None)
				issues = filter_issues_by_scope(raw_issues, run_scope, False, 1)
				issues = filter_issues_by_max_release_date(issues, args.max_release_date)
				if issues:
					return page, issues
			except Exception:
				continue
	raise RuntimeError("; ".join(errors[:5]) if errors else "no Fandom page candidates")


def fandom_page_candidates(run: dict[str, object]) -> list[str]:
	run_id = str(run["id"])
	if run_id in FANDOM_PAGE_OVERRIDES:
		override_pages = FANDOM_PAGE_OVERRIDES[run_id]
	else:
		override_pages = []
	title = str(run["title"])
	volume = str(run["volume"] or "1")
	titles = [
		title,
		remove_leading_article(title),
		title.replace("&", "and"),
		title.replace(" and ", " & "),
		title.replace("Vs.", "vs."),
		title.replace("Vs.", "VS."),
	]
	pages = [normalize_page_title(page) for page in override_pages]
	for candidate_title in titles:
		normalized_title = normalize_page_title(candidate_title)
		pages.append(f"{normalized_title}_Vol_{volume}")
		pages.append(f"{normalized_title}_Vol_{volume}_1")
	return dedupe(pages)


def write_issues(
	args: argparse.Namespace, run_id: str, fandom_page: str, issues: list[FandomIssue]
) -> None:
	namespace = SimpleNamespace(
		run_id=run_id,
		refresh_existing=args.refresh_existing,
		fandom_page=fandom_page,
	)
	with connect_database(args.db) as connection:
		run_scope = fetch_run_scope(connection, run_id)
		for issue in issues:
			upsert_issue(connection, namespace, run_scope, issue)
		append_import_note(connection, namespace, run_scope, issues)


def expected_count_as_int(value: object) -> int | None:
	return int(value) if value is not None else None


def normalize_page_title(value: str) -> str:
	return re.sub(r"\s+", "_", value.strip()).replace(" ", "_")


def remove_leading_article(value: str) -> str:
	return re.sub(r"^The\s+", "", value.strip(), flags=re.I)


def dedupe(values: list[str]) -> list[str]:
	seen: set[str] = set()
	deduped: list[str] = []
	for value in values:
		key = value.casefold()
		if not value or key in seen:
			continue
		seen.add(key)
		deduped.append(value)
	return deduped


def print_result(result: ImportResult) -> None:
	expected = result.expected_count if result.expected_count is not None else "unknown"
	message = f" - {result.message}" if result.message else ""
	page = f" via {result.page}" if result.page else ""
	print(
		f"{result.status}: {result.run_id} {result.title} "
		f"({result.imported_count}/{expected}){page}{message}",
		flush=True,
	)


def print_summary(results: list[ImportResult]) -> None:
	counts: dict[str, int] = {}
	for result in results:
		counts[result.status] = counts.get(result.status, 0) + 1
	print("Summary:")
	for status, count in sorted(counts.items()):
		print(f"  {status}: {count}")


if __name__ == "__main__":
	raise SystemExit(main())
