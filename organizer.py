"""Command-line entry point for organizing Tachidesk comic downloads."""

from __future__ import annotations

import argparse
import sys

from config import ConfigError, load_config
from matcher import candidate_match_key, entry_match_key, match_candidates
from parser import parse_source_files
from processor import find_existing_positions, process_matches
from reading_order import ReadingOrderError, read_reading_order
from scanner import scan_source_folders


def main(argv: list[str] | None = None) -> int:
	args = _parse_args(argv)

	try:
		config = load_config(args.config)
		reading_order = read_reading_order(config.reading_order_path, config.issue_overrides)
	except (ConfigError, ReadingOrderError) as exc:
		print(f"ERROR {exc}", file=sys.stderr)
		return 1

	existing_positions = find_existing_positions(config.destination_folder)
	pending_reading_order, completed_reading_order = split_existing_entries(reading_order, existing_positions)
	source_files = scan_source_folders(config.source_folders)
	candidates = parse_source_files(source_files)
	candidates = filter_completed_candidates(candidates, completed_reading_order)
	match_result = match_candidates(pending_reading_order, candidates)

	if completed_reading_order:
		print(f"SKIP already organized: {len(completed_reading_order)} entries found in destination")
	_report_match_warnings(match_result)
	summary = process_matches(match_result.matches, config.destination_folder, dry_run=args.dry_run)
	print(f"Summary: moved={summary.moved} skipped={summary.skipped} failed={summary.failed}")
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
	completed_keys = {entry_match_key(entry) for entry in completed_entries}
	return tuple(candidate for candidate in candidates if candidate_match_key(candidate) not in completed_keys)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Organize downloaded comic issues into reading order.")
	parser.add_argument("--config", default="config.json", help="Path to organizer config JSON. Defaults to config.json.")
	parser.add_argument("--dry-run", action="store_true", help="Print planned moves without changing files.")
	return parser.parse_args(argv)


def _report_match_warnings(match_result) -> None:
	for duplicate in match_result.duplicate_candidates:
		print(
			"WARN duplicate candidate left in place: "
			f"{duplicate.duplicate.source_path} matches {duplicate.entry.run} #{duplicate.entry.issue_label}; "
			f"winner is {duplicate.winner.source_path}"
		)

	for candidate in match_result.unmatched_candidates:
		print(f"WARN unmatched candidate left in place: {candidate.source_path} ({candidate.run} #{candidate.issue_number})")


if __name__ == "__main__":
	raise SystemExit(main())
