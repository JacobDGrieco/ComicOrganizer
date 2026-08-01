"""Parse normalized comic filenames into database-backed match candidates."""

from __future__ import annotations

import re

from .issue_numbers import comparable_issue_number
from .models import ParsedCandidate, SourceFile


_ISSUE_TOKEN = r"(?P<issue>-?\d+(?:\.[A-Za-z0-9]+)?|[A-Za-z0-9][A-Za-z0-9._-]*|[\u00bc\u00bd\u00be])"
_START_YEAR_TOKEN = r"(?:\((?P<start_year_paren>\d{4})\)|(?P<start_year>\d{4}))"
_ANNUAL_RELEASE_YEAR_RE = re.compile(
	rf"^(?P<title>.+?)\s+{_START_YEAR_TOKEN}\s+Annual\s+['\u2019](?P<short_year>\d{{2}})$",
	re.IGNORECASE,
)
_ANNUAL_ISSUE_RE = re.compile(
	rf"^(?P<title>.+?)\s+{_START_YEAR_TOKEN}\s+Annual\s+#\s*{_ISSUE_TOKEN}$",
	re.IGNORECASE,
)
_SPECIAL_ISSUE_RE = re.compile(
	rf"^(?P<title>.+?)\s+{_START_YEAR_TOKEN}\s+Special\s+#\s*{_ISSUE_TOKEN}$",
	re.IGNORECASE,
)
_REGULAR_ISSUE_RE = re.compile(
	rf"^(?P<title>.+?)\s+{_START_YEAR_TOKEN}\s+#\s*{_ISSUE_TOKEN}$",
	re.IGNORECASE,
)
_REGULAR_ISSUE_YEAR_AFTER_RE = re.compile(
	rf"^(?P<title>.+?)\s+#\s*{_ISSUE_TOKEN}\s+{_START_YEAR_TOKEN}$",
	re.IGNORECASE,
)


def parse_source_files(source_files: tuple[SourceFile, ...]) -> tuple[ParsedCandidate, ...]:
	candidates: list[ParsedCandidate] = []
	for source_file in source_files:
		candidate = parse_source_file(source_file)
		if candidate is not None:
			candidates.append(candidate)

	return tuple(candidates)


def parse_source_file(source_file: SourceFile) -> ParsedCandidate | None:
	"""Parse the configured normalized filename formats."""
	stem = source_file.path.stem.strip()

	match = _ANNUAL_RELEASE_YEAR_RE.match(stem)
	if match:
		return _candidate(
			source_file,
			filename_title=match.group("title"),
			run_start_year=_matched_start_year(match),
			issue_number="",
			is_annual=True,
			annual_release_year=_full_year(match.group("short_year")),
		)

	match = _ANNUAL_ISSUE_RE.match(stem)
	if match:
		return _candidate(
			source_file,
			filename_title=match.group("title"),
			run_start_year=_matched_start_year(match),
			issue_number=match.group("issue"),
			is_annual=True,
		)

	match = _SPECIAL_ISSUE_RE.match(stem)
	if match:
		return _candidate(
			source_file,
			filename_title=match.group("title"),
			run_start_year=_matched_start_year(match),
			issue_number=match.group("issue"),
			is_annual=False,
			is_special=True,
		)

	match = _REGULAR_ISSUE_RE.match(stem)
	if match:
		return _candidate(
			source_file,
			filename_title=match.group("title"),
			run_start_year=_matched_start_year(match),
			issue_number=match.group("issue"),
			is_annual=False,
		)

	match = _REGULAR_ISSUE_YEAR_AFTER_RE.match(stem)
	if match:
		return _candidate(
			source_file,
			filename_title=match.group("title"),
			run_start_year=_matched_start_year(match),
			issue_number=match.group("issue"),
			is_annual=False,
		)

	return None


def _candidate(
	source_file: SourceFile,
	*,
	filename_title: str,
	run_start_year: str,
	issue_number: str,
	is_annual: bool,
	is_special: bool = False,
	annual_release_year: str = "",
) -> ParsedCandidate:
	if is_annual:
		run = source_file.annual_run
		volume = source_file.annual_volume
	elif is_special:
		run = source_file.special_run
		volume = source_file.special_volume
	else:
		run = source_file.run
		volume = source_file.volume
	normalized_issue_number = comparable_issue_number(issue_number) if issue_number else ""
	if normalized_issue_number:
		normalized_issue_number = (source_file.issue_aliases or {}).get(
			normalized_issue_number,
			normalized_issue_number,
		)
	return ParsedCandidate(
		run=run,
		volume=volume,
		issue_number=normalized_issue_number,
		is_annual=is_annual,
		source_path=source_file.path,
		raw_name=source_file.path.name,
		source_order=source_file.source_order,
		filename_title=filename_title.strip(),
		run_start_year=run_start_year,
		annual_release_year=annual_release_year,
		annual_start_year=source_file.annual_start_year,
		is_special=is_special,
	)


def _full_year(short_year: str) -> str:
	year = int(short_year)
	century = 1900 if year >= 50 else 2000
	return str(century + year)


def _matched_start_year(match: re.Match[str]) -> str:
	return match.group("start_year_paren") or match.group("start_year")
