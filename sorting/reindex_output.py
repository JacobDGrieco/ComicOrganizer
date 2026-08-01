"""Reindex existing organized files against the current reading order."""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import ConfigError, load_config
from .logging import default_log_path, write_log
from .matcher import candidate_matches_entry, canonical_filename
from .issue_numbers import comparable_issue_number
from .models import DuplicateCandidate, MatchedComic, MatchResult, OrganizerConfig, ParsedCandidate, ReadingOrderEntry, SourceFile
from .parser import parse_source_file
from .reading_order import ReadingOrderError, read_reading_order


PREFIXED_OUTPUT_RE = re.compile(r"^(?P<position>\d{4,5}) - (?P<original_name>.+)$")


class ReindexError(ValueError):
	pass


@dataclass(frozen=True)
class OutputFile:
	path: Path
	position: int
	original_name: str


@dataclass(frozen=True)
class ReindexPlanItem:
	source_path: Path
	destination_path: Path
	old_position: int
	new_position: int


@dataclass(frozen=True)
class ReindexPlan:
	items: tuple[ReindexPlanItem, ...]
	warnings: tuple[str, ...]


def plan_reindex(config: OrganizerConfig, *, folder: str | Path | None = None) -> ReindexPlan:
	"""Build a validated rename plan from existing output files to current DB order."""
	output_folder = Path(folder) if folder else config.destination_folder
	if not output_folder.is_dir():
		raise ReindexError(f"Output folder does not exist: {output_folder}")

	reading_order = read_reading_order(config.reading_order_path, config.issue_overrides)
	output_files = output_files_from_folder(output_folder)
	candidates, candidate_paths = parse_output_files(output_files, config, reading_order)
	match_result = match_reindex_candidates(reading_order, tuple(candidates), candidate_paths)

	matches_by_path: dict[Path, list] = {}
	for match in match_result.matches:
		actual_path = candidate_paths[match.source_path]
		matches_by_path.setdefault(actual_path, []).append(match)

	warnings = build_warnings(output_files, candidates, candidate_paths, match_result, matches_by_path)
	items: list[ReindexPlanItem] = []
	for output_file in output_files:
		matches = matches_by_path.get(output_file.path, [])
		if len(matches) != 1:
			continue

		match = matches[0]
		destination_path = output_file.path.with_name(match.canonical_name)
		items.append(
			ReindexPlanItem(
				source_path=output_file.path,
				destination_path=destination_path,
				old_position=output_file.position,
				new_position=match.position,
			)
		)

	validate_plan(output_folder, items)
	return ReindexPlan(items=tuple(sorted(items, key=lambda item: item.old_position)), warnings=tuple(warnings))


def output_files_from_folder(folder: Path) -> tuple[OutputFile, ...]:
	files: list[OutputFile] = []
	for path in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
		if not path.is_file():
			continue
		if path.suffix.casefold() != ".cbz":
			continue

		match = PREFIXED_OUTPUT_RE.match(path.name)
		if match is None:
			continue

		files.append(
			OutputFile(
				path=path,
				position=int(match.group("position")),
				original_name=match.group("original_name"),
			)
		)

	return tuple(files)


def parse_output_files(
	output_files: tuple[OutputFile, ...],
	config: OrganizerConfig,
	reading_order: tuple[ReadingOrderEntry, ...] = (),
) -> tuple[list[ParsedCandidate], dict[Path, Path]]:
	candidates: list[ParsedCandidate] = []
	candidate_paths: dict[Path, Path] = {}
	for file_index, output_file in enumerate(output_files, start=1):
		output_candidate_count = 0
		year_mismatch_candidates: list[ParsedCandidate] = []
		for source_index, source_folder in enumerate(config.source_folders, start=1):
			virtual_path = (
				output_file.path.parent
				/ f".reindex-{file_index:05d}-{source_index:05d}"
				/ output_file.original_name
			)
			source_file = SourceFile(
				path=virtual_path,
				run=source_folder.run,
				volume=source_folder.volume,
				source_order=file_index * 1000 + source_index,
				annual_run=source_folder.annual_run,
				annual_volume=source_folder.annual_volume,
				annual_start_year=source_folder.annual_start_year,
				special_run=source_folder.special_run,
				special_volume=source_folder.special_volume,
				issue_aliases=source_folder.issue_aliases,
			)
			candidate = parse_source_file(source_file)
			if candidate is None:
				continue
			if not title_matches_source(candidate, source_folder):
				continue
			if source_folder_start_year(source_folder.path) not in {"", candidate.run_start_year}:
				year_mismatch_candidates.append(candidate)
				continue
			candidates.append(candidate)
			candidate_paths[candidate.source_path] = output_file.path
			output_candidate_count += 1

		if output_candidate_count == 0:
			if year_mismatch_candidates:
				for candidate in year_mismatch_candidates:
					candidates.append(candidate)
					candidate_paths[candidate.source_path] = output_file.path
			else:
				fallback_candidate = fallback_candidate_from_reading_order(output_file, reading_order, file_index)
				if fallback_candidate is not None:
					candidates.append(fallback_candidate)
					candidate_paths[fallback_candidate.source_path] = output_file.path

	return candidates, candidate_paths


def fallback_candidate_from_reading_order(
	output_file: OutputFile,
	reading_order: tuple[ReadingOrderEntry, ...],
	file_index: int,
) -> ParsedCandidate | None:
	"""Parse already-organized files whose original source folder is no longer configured."""
	virtual_path = output_file.path.parent / f".reindex-{file_index:05d}-fallback" / output_file.original_name
	probe = parse_source_file(
		SourceFile(
			path=virtual_path,
			run="",
			volume="1",
			source_order=file_index * 1000 + 999,
		)
	)
	if probe is None:
		return None

	matching_entries = [
		entry
		for entry in reading_order
		if title_key(entry.run) == title_key(probe.filename_title)
		and entry.run_start_year == probe.run_start_year
		and comparable_issue_number(entry.issue_label) == comparable_issue_number(probe.issue_number)
	]
	if len(matching_entries) != 1:
		return None

	entry = matching_entries[0]
	return ParsedCandidate(
		run=entry.run,
		volume=entry.volume,
		issue_number=probe.issue_number,
		is_annual=probe.is_annual,
		source_path=probe.source_path,
		raw_name=probe.raw_name,
		source_order=probe.source_order,
		filename_title=probe.filename_title,
		run_start_year=probe.run_start_year,
		annual_release_year=probe.annual_release_year,
		annual_start_year=probe.annual_start_year,
		is_special=probe.is_special,
	)


def match_reindex_candidates(
	reading_order,
	candidates: tuple[ParsedCandidate, ...],
	candidate_paths: dict[Path, Path],
) -> MatchResult:
	"""Match reindex candidates while preferring files already at their current target."""
	sorted_candidates = tuple(
		sorted(candidates, key=lambda candidate: (candidate.source_order, candidate.raw_name.casefold()))
	)
	matches: list[MatchedComic] = []
	unmatched_entries = []
	duplicate_candidates: list[DuplicateCandidate] = []
	used_candidate_ids: set[int] = set()

	for entry in reading_order:
		entry_candidates = [
			candidate
			for candidate in sorted_candidates
			if id(candidate) not in used_candidate_ids and candidate_matches_entry(candidate, entry)
		]
		if not entry_candidates:
			unmatched_entries.append(entry)
			continue

		winner = min(
			entry_candidates,
			key=lambda candidate: reindex_candidate_rank(entry, candidate, candidate_paths),
		)
		used_candidate_ids.add(id(winner))
		matches.append(
			MatchedComic(
				position=entry.position,
				run=entry.run,
				issue_label=entry.issue_label,
				canonical_name=canonical_filename(entry, winner),
				source_path=winner.source_path,
				is_annual=winner.is_annual,
			)
		)

		for duplicate in entry_candidates:
			if duplicate is winner:
				continue
			used_candidate_ids.add(id(duplicate))
			duplicate_candidates.append(DuplicateCandidate(entry=entry, winner=winner, duplicate=duplicate))

	unmatched_candidates = tuple(
		candidate
		for candidate in candidates
		if id(candidate) not in used_candidate_ids
	)

	return MatchResult(
		matches=tuple(sorted(matches, key=lambda match: match.position)),
		unmatched_entries=tuple(unmatched_entries),
		unmatched_candidates=unmatched_candidates,
		duplicate_candidates=tuple(duplicate_candidates),
	)


def reindex_candidate_rank(entry, candidate: ParsedCandidate, candidate_paths: dict[Path, Path]) -> tuple[int, int, str]:
	actual_path = candidate_paths[candidate.source_path]
	target_name = canonical_filename(entry, candidate).casefold()
	current_name = actual_path.name.casefold()
	is_already_target = current_name == target_name
	return (0 if is_already_target else 1, candidate.source_order, candidate.raw_name.casefold())


def source_folder_start_year(path: Path) -> str:
	match = re.search(r"\((\d{4})\)", path.name)
	if match:
		return match.group(1)
	match = re.search(r"\b(\d{4})\b", path.name)
	return match.group(1) if match else ""


def title_matches_source(candidate: ParsedCandidate, source_folder) -> bool:
	expected_titles = {source_folder.run}
	if candidate.is_annual:
		expected_titles.add(re.sub(r"\s+annual\s*$", "", source_folder.annual_run, flags=re.I))
	if candidate.is_special:
		expected_titles.add(re.sub(r"\s+special\s*$", "", source_folder.special_run, flags=re.I))
	return title_key(candidate.filename_title) in {title_key(title) for title in expected_titles if title}


def title_key(value: str) -> str:
	text = re.sub(r"^the\s+", "", value.strip(), flags=re.I)
	text = re.sub(r"[^A-Za-z0-9]+", " ", text).casefold().strip()
	return re.sub(r"^the\s+", "", text, flags=re.I)


def build_warnings(output_files, candidates, candidate_paths, match_result, matches_by_path) -> list[str]:
	warnings: list[str] = []
	candidate_paths_by_output = {
		candidate_paths[candidate.source_path]
		for candidate in candidates
	}
	for output_file in output_files:
		if output_file.path not in candidate_paths_by_output:
			if can_parse_original_filename(output_file):
				warnings.append(f"{output_file.path.name}: no configured source title matched original filename; skipped")
			else:
				warnings.append(f"{output_file.path.name}: could not parse original filename; skipped")
			continue
		if len(matches_by_path.get(output_file.path, [])) > 1:
			warnings.append(f"{output_file.path.name}: matched multiple current reading-order entries; skipped")

	matched_paths = set(matches_by_path)
	duplicate_paths = {
		candidate_paths[duplicate.duplicate.source_path]
		for duplicate in match_result.duplicate_candidates
		if duplicate.duplicate.source_path in candidate_paths
	}
	unmatched_paths = {
		candidate_paths[candidate.source_path]
		for candidate in match_result.unmatched_candidates
		if candidate.source_path in candidate_paths
	}
	for path in sorted(unmatched_paths - matched_paths - duplicate_paths, key=lambda item: item.name.casefold()):
		warnings.append(f"{path.name}: no current reading-order match; skipped")

	for duplicate in match_result.duplicate_candidates:
		duplicate_path = candidate_paths.get(duplicate.duplicate.source_path)
		winner_path = candidate_paths.get(duplicate.winner.source_path)
		if duplicate_path is None or winner_path is None:
			continue
		warnings.append(
			f"{duplicate_path.name}: duplicate match for {duplicate.entry.run} "
			f"v{duplicate.entry.volume} #{duplicate.entry.issue_label}; "
			f"winner is {winner_path.name}"
		)

	return warnings


def can_parse_original_filename(output_file: OutputFile) -> bool:
	probe = parse_source_file(
		SourceFile(
			path=output_file.path.parent / ".reindex-parse-check" / output_file.original_name,
			run="",
			volume="1",
			source_order=0,
		)
	)
	return probe is not None


def validate_plan(folder: Path, items: list[ReindexPlanItem]) -> None:
	target_positions: set[int] = set()
	target_names: set[str] = set()
	source_names = {item.source_path.name.casefold() for item in items}
	existing_names = {path.name.casefold() for path in folder.iterdir() if path.is_file()}

	for item in items:
		if item.new_position in target_positions:
			raise ReindexError(f"Reindex would create duplicate target position: {item.new_position:05d}")
		target_positions.add(item.new_position)

		target_name = item.destination_path.name.casefold()
		if target_name in target_names:
			raise ReindexError(f"Reindex would create duplicate target filename: {item.destination_path.name}")
		if target_name in existing_names and target_name not in source_names:
			raise ReindexError(f"Target already exists outside reindex plan: {item.destination_path.name}")
		target_names.add(target_name)


def apply_reindex(plan: ReindexPlan) -> None:
	"""Rename files through temporary names so position swaps are safe."""
	rename_items = [item for item in plan.items if item.source_path != item.destination_path]
	temporary_moves: list[tuple[Path, Path, Path]] = []

	for item in rename_items:
		temp_path = item.source_path.with_name(f".reindex-{uuid.uuid4().hex}-{item.source_path.name}")
		item.source_path.rename(temp_path)
		temporary_moves.append((temp_path, item.destination_path, item.source_path))

	try:
		for temp_path, destination_path, _source_path in temporary_moves:
			temp_path.rename(destination_path)
	except OSError:
		for temp_path, _destination_path, source_path in temporary_moves:
			if temp_path.exists() and not source_path.exists():
				temp_path.rename(source_path)
		raise


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv)
	try:
		config = load_config(args.config)
		plan = plan_reindex(config, folder=args.folder)
	except (ConfigError, ReadingOrderError, ReindexError) as exc:
		lines = [f"ERROR {exc}"]
		print(lines[0], file=sys.stderr)
		write_log(log_path(args), lines)
		return 1

	lines = render_plan(plan, apply=args.apply)
	for line in lines:
		print(line)
	write_log(log_path(args), lines)

	if args.apply:
		try:
			apply_reindex(plan)
		except OSError as exc:
			error_lines = [f"ERROR rename failed: {exc}"]
			print(error_lines[0], file=sys.stderr)
			write_log(log_path(args), lines + error_lines)
			return 1
		applied_lines = [f"Renamed {changed_count(plan)} file(s)."]
		for line in applied_lines:
			print(line)
		write_log(log_path(args), lines + applied_lines)

	return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Reindex existing output filenames against the current configured reading order."
	)
	parser.add_argument("--config", default="config.json", help="Organizer config JSON. Defaults to config.json.")
	parser.add_argument("--folder", help="Output folder. Defaults to config destination_folder.")
	parser.add_argument("--log", help="Log file. Defaults to logs/reindex-output.log next to the config file.")
	parser.add_argument("--apply", action="store_true", help="Actually rename files. Without this, only prints the plan.")
	return parser.parse_args(argv)


def render_plan(plan: ReindexPlan, *, apply: bool) -> list[str]:
	lines: list[str] = []
	for warning in plan.warnings:
		lines.append(f"WARN {warning}")

	changed_items = [item for item in plan.items if item.source_path != item.destination_path]
	for item in changed_items:
		action = "rename" if apply else "would rename"
		lines.append(f"{action}: {item.source_path.name} -> {item.destination_path.name}")

	if not changed_items:
		lines.append("No index changes needed.")
	elif not apply:
		lines.append(f"Dry run only. {len(changed_items)} file(s) would be renamed. Pass --apply to rename files.")

	return lines


def changed_count(plan: ReindexPlan) -> int:
	return sum(1 for item in plan.items if item.source_path != item.destination_path)


def log_path(args: argparse.Namespace) -> Path:
	return Path(args.log) if args.log else default_log_path(args.config, "reindex-output.log")


if __name__ == "__main__":
	raise SystemExit(main())
