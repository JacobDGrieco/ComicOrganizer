"""Parse Tachidesk comic filenames into matchable issue candidates."""

from __future__ import annotations

import re

from issue_numbers import comparable_issue_number, normalize_volume_label
from models import ParsedCandidate, SourceFile


_ISSUE_HASH_RE = re.compile(r"^Issue\s*#?\s*(?P<issue>\d+)\s*$", re.IGNORECASE)
_SIMPLE_ANNUAL_RE = re.compile(r"^Annual(?:\s*#?|\s*[_-]\s*)+(?P<issue>\d+)(?:\s*\([^)]*\))?\s*$", re.IGNORECASE)
_ANNUAL_RE = re.compile(r"^v\s*(?P<volume>\d+)\b.*\bannual\b\D*(?P<issue>\d+)\s*$", re.IGNORECASE)
_VOLUME_ISSUE_RE = re.compile(r"^v\s*(?P<volume>\d+)\D+(?P<issue>\d+)\s*$", re.IGNORECASE)
_LEADING_ISSUE_TITLE_RE = re.compile(r"^(?P<issue>\d+)(?:\s*[_-]\s*)+.+$", re.IGNORECASE)


def parse_source_files(source_files: tuple[SourceFile, ...]) -> tuple[ParsedCandidate, ...]:
	candidates: list[ParsedCandidate] = []
	for source_file in source_files:
		candidate = parse_source_file(source_file)
		if candidate is not None:
			candidates.append(candidate)

	return tuple(candidates)


def parse_source_file(source_file: SourceFile) -> ParsedCandidate | None:
	stem = source_file.path.stem.strip()

	match = _ISSUE_HASH_RE.match(stem)
	if match:
		return _candidate(source_file, match.group("issue"), is_annual=False)

	match = _SIMPLE_ANNUAL_RE.match(stem)
	if match:
		return _candidate(source_file, match.group("issue"), is_annual=True)

	match = _ANNUAL_RE.match(stem)
	if match:
		return _candidate(source_file, match.group("issue"), is_annual=True, filename_volume=match.group("volume"))

	match = _VOLUME_ISSUE_RE.match(stem)
	if match:
		return _candidate(source_file, match.group("issue"), is_annual=False, filename_volume=match.group("volume"))

	match = _LEADING_ISSUE_TITLE_RE.match(stem)
	if match:
		return _candidate(source_file, match.group("issue"), is_annual=False)

	return None


def _candidate(source_file: SourceFile, issue_number: str, is_annual: bool, filename_volume: str | None = None) -> ParsedCandidate:
	run = source_file.run
	output_name = source_file.output_name or source_file.run
	volume = normalize_volume_label(filename_volume or source_file.volume)
	if is_annual:
		run = source_file.annual_run or _annual_name(run)
		output_name = source_file.annual_output_name or _annual_name(output_name)
		volume = normalize_volume_label(filename_volume or source_file.annual_volume or volume)

	return ParsedCandidate(
		run=run,
		volume=volume,
		issue_number=comparable_issue_number(issue_number),
		is_annual=is_annual,
		source_path=source_file.path,
		raw_name=source_file.path.name,
		source_order=source_file.source_order,
		output_name=output_name,
	)


def _annual_name(run_name: str) -> str:
	if run_name.casefold().endswith(" annual"):
		return run_name

	return f"{run_name} Annual"
