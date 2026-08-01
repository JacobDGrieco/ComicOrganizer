"""Command-line entry point for organizing Tachidesk comic downloads."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .logging import append_log, default_log_path, write_log
from .matcher import candidate_matches_entry, match_candidates
from .parser import parse_source_files
from .processor import find_existing_positions, process_matches
from .reading_order import ReadingOrderError, read_reading_order
from .scanner import scan_source_folders


def main(argv: list[str] | None = None) -> int:
	args = _parse_args(argv)
	config = None

	try:
		config = load_config(args.config)
		reading_order = read_reading_order(config.reading_order_path, config.issue_overrides)
	except (ConfigError, ReadingOrderError) as exc:
		error_lines = [f"ERROR {exc}"]
		print(error_lines[0], file=sys.stderr)
		log_path = config.log_path if config is not None else default_log_path(args.config, "comic-organizer.log")
		write_log(log_path, error_lines)
		return 1

	existing_positions = find_existing_positions(config.destination_folder)
	pending_reading_order, completed_reading_order = split_existing_entries(reading_order, existing_positions)
	skipped_source_folders = unreachable_source_folders(config.source_folders)
	source_files = scan_source_folders(config.source_folders)
	candidates = parse_source_files(source_files)
	unparsed_source_files = unparsed_files(source_files, candidates)
	candidates = filter_completed_candidates(candidates, completed_reading_order)
	match_result = match_candidates(pending_reading_order, candidates)

	report_lines = build_report_lines(match_result, completed_reading_order, unparsed_source_files, skipped_source_folders)
	for line in report_lines:
		print(line)
	write_log(config.log_path, report_lines)
	summary = process_matches(match_result.matches, config.destination_folder, dry_run=args.dry_run, verbose=False)
	result_lines = build_result_lines(summary, dry_run=args.dry_run)
	for line in result_lines:
		print(line)
	append_log(config.log_path, result_lines)
	return 1 if summary.failed else 0


def split_existing_entries(reading_order, existing_positions: frozenset[int]):
	pending_entries = []
	completed_entries = []
	for entry in reading_order:
		if entry.position in existing_positions:
			completed_entries.append(entry)
		else:
			pending_entries.append(entry)

	return tuple(pending_entries), tuple(completed_entries)


def filter_completed_candidates(candidates, completed_entries):
	return tuple(
		candidate
		for candidate in candidates
		if not any(candidate_matches_entry(candidate, entry) for entry in completed_entries)
	)


def unparsed_files(source_files, candidates):
	parsed_paths = {candidate.source_path for candidate in candidates}
	return tuple(source_file for source_file in source_files if source_file.path not in parsed_paths)


def unreachable_source_folders(source_folders):
	return tuple(source_folder for source_folder in source_folders if not source_folder.path.is_dir())


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Organize downloaded comic issues into reading order.")
	parser.add_argument("--config", default="config.json", help="Path to organizer config JSON. Defaults to config.json.")
	parser.add_argument("--dry-run", action="store_true", help="Print planned moves without changing files.")
	return parser.parse_args(argv)


def build_report_lines(match_result, completed_reading_order, unparsed_source_files, skipped_source_folders) -> list[str]:
	lines: list[str] = []
	lines.append("Unmatched scanned files:")
	if unparsed_source_files or match_result.unmatched_candidates:
		for source_file in sorted(unparsed_source_files, key=lambda item: display_path(item.path).casefold()):
			lines.append(f"  {display_path(source_file.path)}")
		for candidate in sorted(match_result.unmatched_candidates, key=lambda item: display_path(item.source_path).casefold()):
			lines.append(f"  {display_path(candidate.source_path)}")
	else:
		lines.append("  (none)")

	lines.append("")
	lines.append("Conversions:")
	if match_result.matches:
		for match in match_result.matches:
			lines.append(f"  {display_path(match.source_path)} -> {match.canonical_name}")
	else:
		lines.append("  (none)")

	if match_result.duplicate_candidates:
		lines.append("")
		lines.append("Duplicate scanned files:")
		for duplicate in match_result.duplicate_candidates:
			lines.append(
				"  "
				f"{display_path(duplicate.duplicate.source_path)} matches "
				f"{duplicate.entry.run} #{duplicate.entry.issue_label}; "
				f"winner is {display_path(duplicate.winner.source_path)}"
			)

	if completed_reading_order:
		lines.append("")
		lines.append(f"Already organized positions skipped: {len(completed_reading_order)}")

	if skipped_source_folders:
		lines.append("")
		lines.append("Skipped source folders:")
		for source_folder in skipped_source_folders:
			lines.append(f"  {source_folder.path}")

	return lines


def build_result_lines(summary, *, dry_run: bool) -> list[str]:
	planned = sum(1 for result in summary.results if result.action == "dry_run")
	lines = [""]
	if dry_run:
		lines.append(f"Summary: planned={planned} moved=0 skipped={summary.skipped} failed={summary.failed}")
	else:
		lines.append(f"Summary: moved={summary.moved} skipped={summary.skipped} failed={summary.failed}")
	failures = [result for result in summary.results if result.action == "failed"]
	if failures:
		lines.append("")
		lines.append("Failures:")
		for failure in failures:
			lines.append(f"  {display_path(failure.match.source_path)} -> {failure.destination_path.name}: {failure.error}")
	return lines


def display_path(path: Path) -> str:
	parent = path.parent.name or str(path.parent)
	return f"{parent}\\{path.name}"


if __name__ == "__main__":
	raise SystemExit(main())
