"""Shared data structures for the comic organizer pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceFolderConfig:
	path: Path
	run: str
	volume: str
	annual_run: str = ""
	annual_volume: str = ""
	annual_start_year: str = ""
	special_run: str = ""
	special_volume: str = ""
	issue_aliases: dict[str, str] | None = None
	source_title_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrganizerConfig:
	reading_order_path: Path
	destination_folder: Path
	log_path: Path
	source_folders: tuple[SourceFolderConfig, ...]
	issue_overrides: dict[str, dict[str, str]]
	project_name: str = ""
	character_list_path: Path | None = None


@dataclass(frozen=True)
class ReadingOrderEntry:
	position: int
	run: str
	issue_label: str
	volume: str = "1"
	run_years: str = ""
	run_start_year: str = ""
	release_date: str = ""


@dataclass(frozen=True)
class SourceFile:
	path: Path
	run: str
	volume: str
	source_order: int
	annual_run: str = ""
	annual_volume: str = ""
	annual_start_year: str = ""
	special_run: str = ""
	special_volume: str = ""
	issue_aliases: dict[str, str] | None = None


@dataclass(frozen=True)
class ParsedCandidate:
	run: str
	volume: str
	issue_number: str
	is_annual: bool
	source_path: Path
	raw_name: str
	source_order: int
	filename_title: str = ""
	run_start_year: str = ""
	annual_release_year: str = ""
	annual_start_year: str = ""
	is_special: bool = False


@dataclass(frozen=True)
class MatchedComic:
	position: int
	run: str
	issue_label: str
	canonical_name: str
	source_path: Path
	is_annual: bool = False


@dataclass(frozen=True)
class DuplicateCandidate:
	entry: ReadingOrderEntry
	winner: ParsedCandidate
	duplicate: ParsedCandidate


@dataclass(frozen=True)
class MatchResult:
	matches: tuple[MatchedComic, ...]
	unmatched_entries: tuple[ReadingOrderEntry, ...]
	unmatched_candidates: tuple[ParsedCandidate, ...]
	duplicate_candidates: tuple[DuplicateCandidate, ...]


@dataclass(frozen=True)
class MoveResult:
	match: MatchedComic
	action: str
	destination_path: Path
	error: str | None = None


@dataclass(frozen=True)
class ProcessSummary:
	moved: int
	skipped: int
	failed: int
	results: tuple[MoveResult, ...]
