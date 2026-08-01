"""List configured comic runs and every issue in reading-order position order."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import ConfigError, load_config
from .logging import default_log_path, write_log
from .models import ReadingOrderEntry
from .reading_order import ReadingOrderError, read_reading_order


@dataclass(frozen=True)
class ComicRunSummary:
	position: int
	run: str
	volume: str
	years: str


@dataclass(frozen=True)
class ReadingOrderListReport:
	runs: tuple[ComicRunSummary, ...]
	entries: tuple[ReadingOrderEntry, ...]


def build_list_report(reading_order: tuple[ReadingOrderEntry, ...]) -> ReadingOrderListReport:
	"""Build the ordered run list and full issue list from reading-order entries."""
	seen_runs: set[tuple[str, str]] = set()
	runs: list[ComicRunSummary] = []
	for entry in reading_order:
		run_key = (entry.run.casefold(), entry.volume)
		if run_key in seen_runs:
			continue
		seen_runs.add(run_key)
		runs.append(
			ComicRunSummary(
				position=entry.position,
				run=entry.run,
				volume=entry.volume,
				years=entry.run_years,
			)
		)

	return ReadingOrderListReport(runs=tuple(runs), entries=reading_order)


def format_report(report: ReadingOrderListReport) -> list[str]:
	"""Render the run list and full reading order as stable terminal/log lines."""
	lines: list[str] = []
	lines.append("Comic runs:")
	if not report.runs:
		lines.append("  (none)")
	else:
		for run in report.runs:
			years = f" ({run.years})" if run.years else ""
			lines.append(f"  {run.position:05d} - {run.run} v{run.volume}{years}")

	lines.append("")
	lines.append("Sort order:")
	if not report.entries:
		lines.append("  (none)")
		return lines

	for entry in report.entries:
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
		report = build_list_report(reading_order)
	except (ConfigError, ReadingOrderError) as exc:
		error_lines = [f"ERROR {exc}"]
		print(error_lines[0], file=sys.stderr)
		write_log(default_list_log_path(args), error_lines)
		return 1

	lines = format_report(report)
	for line in lines:
		print(line)

	write_log(default_list_log_path(args), lines)
	return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="List configured comic runs and full reading-order issues.")
	parser.add_argument("--config", default="config.json", help="Organizer config JSON. Defaults to config.json.")
	parser.add_argument(
		"--output",
		help="Report file path. Defaults to logs/reading-order-list.log next to the config file.",
	)
	return parser.parse_args(argv)


def default_list_log_path(args: argparse.Namespace) -> Path:
	return Path(args.output) if args.output else default_log_path(args.config, "reading-order-list.log")


if __name__ == "__main__":
	raise SystemExit(main())
