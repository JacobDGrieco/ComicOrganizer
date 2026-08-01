"""Report missing organized comics up to the last existing output position."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import ConfigError, load_config
from .logging import default_log_path, write_log
from .models import ReadingOrderEntry
from .processor import find_existing_positions
from .reading_order import ReadingOrderError, read_reading_order


class MissingEntriesError(ValueError):
	pass


@dataclass(frozen=True)
class MissingEntriesReport:
	last_existing_position: int | None
	missing_entries: tuple[ReadingOrderEntry, ...]
	existing_count_in_range: int


def build_missing_entries_report(
	reading_order: tuple[ReadingOrderEntry, ...],
	existing_positions: frozenset[int],
) -> MissingEntriesReport:
	"""Find reading-order entries missing before the highest present destination position."""
	if not existing_positions:
		return MissingEntriesReport(
			last_existing_position=None,
			missing_entries=(),
			existing_count_in_range=0,
		)

	entries_by_position = {entry.position: entry for entry in reading_order}
	last_existing_position = max(existing_positions)
	missing_entries = tuple(
		entries_by_position[position]
		for position in range(1, last_existing_position + 1)
		if position not in existing_positions and position in entries_by_position
	)
	existing_count_in_range = sum(
		1
		for position in existing_positions
		if 1 <= position <= last_existing_position
	)
	return MissingEntriesReport(
		last_existing_position=last_existing_position,
		missing_entries=missing_entries,
		existing_count_in_range=existing_count_in_range,
	)


def format_report(report: MissingEntriesReport) -> list[str]:
	"""Render the report as stable terminal/log lines."""
	lines: list[str] = []
	if report.last_existing_position is None:
		return ["No organized files with numeric prefixes were found."]

	lines.append(f"Last existing output position: {report.last_existing_position:05d}")
	lines.append(f"Existing entries in range: {report.existing_count_in_range}")
	lines.append(f"Missing entries in range: {len(report.missing_entries)}")
	lines.append("")
	lines.append("Missing entries:")
	if not report.missing_entries:
		lines.append("  (none)")
		return lines

	for entry in report.missing_entries:
		release_date = f" ({entry.release_date})" if entry.release_date else ""
		lines.append(
			f"  {entry.position:05d} - {entry.run} v{entry.volume} #{entry.issue_label}{release_date}"
		)

	return lines


def main(argv: list[str] | None = None) -> int:
	args = _parse_args(argv)
	try:
		config = load_config(args.config)
		reading_order = read_reading_order(config.reading_order_path, config.issue_overrides)
		existing_positions = find_existing_positions(config.destination_folder)
		report = build_missing_entries_report(reading_order, existing_positions)
	except (ConfigError, MissingEntriesError, ReadingOrderError) as exc:
		error_lines = [f"ERROR {exc}"]
		print(error_lines[0], file=sys.stderr)
		write_log(default_missing_log_path(args), error_lines)
		return 1

	lines = format_report(report)
	for line in lines:
		print(line)

	write_log(default_missing_log_path(args), lines)
	return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Report reading-order entries missing before the last organized output file."
	)
	parser.add_argument("--config", default="config.json", help="Organizer config JSON. Defaults to config.json.")
	parser.add_argument(
		"--output",
		help="Report file path. Defaults to logs/missing-entries.log next to the config file.",
	)
	return parser.parse_args(argv)


def default_missing_log_path(args: argparse.Namespace) -> Path:
	return Path(args.output) if args.output else default_log_path(args.config, "missing-entries.log")


if __name__ == "__main__":
	raise SystemExit(main())
