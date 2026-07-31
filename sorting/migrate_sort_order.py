"""Renumber existing destination files after the reading-order JSON changes."""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import ConfigError, load_config
from .issue_numbers import comparable_issue_number
from .matcher import entry_match_key
from .models import OrganizerConfig, ReadingOrderEntry
from .reading_order import ReadingOrderError, read_reading_order


DESTINATION_NAME_RE = re.compile(r"^(?P<position>\d{4}) - (?P<title>.+) #(?P<issue>.+)\.cbz$", re.IGNORECASE)


class MigrationError(ValueError):
	pass


@dataclass(frozen=True)
class DestinationComic:
	path: Path
	position: int
	title: str
	issue_label: str


@dataclass(frozen=True)
class MigrationPlanItem:
	source_path: Path
	destination_path: Path
	old_position: int
	new_position: int


@dataclass(frozen=True)
class MigrationPlan:
	items: tuple[MigrationPlanItem, ...]
	warnings: tuple[str, ...]


def plan_migration(
	folder: str | Path,
	new_reading_order_path: str | Path,
	old_reading_order_path: str | Path | None = None,
	config: OrganizerConfig | None = None,
) -> MigrationPlan:
	"""Build a renumbering plan for existing destination files."""
	folder_path = Path(folder)
	if not folder_path.is_dir():
		raise MigrationError(f"Destination folder does not exist: {folder_path}")

	issue_overrides = config.issue_overrides if config is not None else {}
	new_entries = read_reading_order(new_reading_order_path, issue_overrides)
	new_entries_by_match_key = _unique_entry_index(new_entries)
	destination_comics = _destination_comics(folder_path)

	if old_reading_order_path is not None:
		old_entries = read_reading_order(old_reading_order_path, issue_overrides)
		items, warnings = _plan_from_old_order(destination_comics, old_entries, new_entries_by_match_key)
	else:
		items, warnings = _plan_from_filenames(destination_comics, new_entries, config)

	_validate_plan(folder_path, items)
	return MigrationPlan(items=tuple(sorted(items, key=lambda item: item.old_position)), warnings=tuple(warnings))


def apply_migration(plan: MigrationPlan) -> None:
	"""Apply a validated migration plan using temporary filenames first."""
	rename_items = [item for item in plan.items if item.source_path != item.destination_path]
	temporary_moves: list[tuple[Path, Path, Path]] = []

	for item in rename_items:
		temp_path = item.source_path.with_name(f".migration-{uuid.uuid4().hex}-{item.source_path.name}")
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
	args = _parse_args(argv)
	try:
		config = load_config(args.config) if args.config else None
		folder = Path(args.folder) if args.folder else _config_value(config, "destination_folder", "--folder or --config is required")
		new_reading_order = Path(args.new_reading_order) if args.new_reading_order else _config_value(
			config,
			"reading_order_path",
			"--new-reading-order or --config is required",
		)
		plan = plan_migration(
			folder=folder,
			new_reading_order_path=new_reading_order,
			old_reading_order_path=args.old_reading_order,
			config=config,
		)
	except (ConfigError, MigrationError, ReadingOrderError) as exc:
		print(f"ERROR {exc}", file=sys.stderr)
		return 1

	for warning in plan.warnings:
		print(f"WARN {warning}")

	for item in plan.items:
		if item.source_path == item.destination_path:
			continue
		action = "rename" if args.apply else "would rename"
		print(f"{action}: {item.source_path.name} -> {item.destination_path.name}")

	if args.apply:
		try:
			apply_migration(plan)
		except OSError as exc:
			print(f"ERROR rename failed: {exc}", file=sys.stderr)
			return 1
		print(f"Renamed {sum(1 for item in plan.items if item.source_path != item.destination_path)} files.")
	else:
		print(
			"Dry run only. "
			f"{sum(1 for item in plan.items if item.source_path != item.destination_path)} files would be renamed. "
			"Pass --apply to rename files."
		)

	return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Renumber existing destination files against a revised sort-order JSON file.")
	parser.add_argument("--config", help="Organizer config JSON. Provides folder, new reading-order file, and output-name aliases.")
	parser.add_argument("--folder", help="Destination folder containing already organized files.")
	parser.add_argument("--new-reading-order", help="Reworked reading-order JSON path. Defaults to config reading_order_path.")
	parser.add_argument("--old-reading-order", help="Original reading-order JSON path. Recommended when repeated issue numbers exist across volumes.")
	parser.add_argument("--apply", action="store_true", help="Actually rename files. Without this, only prints the plan.")
	return parser.parse_args(argv)


def _config_value(config: OrganizerConfig | None, field_name: str, error_message: str):
	if config is None:
		raise MigrationError(error_message)

	return getattr(config, field_name)


def _destination_comics(folder: Path) -> tuple[DestinationComic, ...]:
	comics: list[DestinationComic] = []
	for path in sorted(folder.iterdir(), key=lambda current_path: current_path.name.casefold()):
		if not path.is_file():
			continue

		match = DESTINATION_NAME_RE.match(path.name)
		if match is None:
			continue

		comics.append(
			DestinationComic(
				path=path,
				position=int(match.group("position")),
				title=match.group("title").strip(),
				issue_label=match.group("issue").strip(),
			)
		)

	return tuple(comics)


def _plan_from_old_order(
	destination_comics: tuple[DestinationComic, ...],
	old_entries: tuple[ReadingOrderEntry, ...],
	new_entries_by_match_key: dict[tuple[str, str, str], ReadingOrderEntry],
) -> tuple[list[MigrationPlanItem], list[str]]:
	old_entries_by_position = {entry.position: entry for entry in old_entries}
	items: list[MigrationPlanItem] = []
	warnings: list[str] = []

	for comic in destination_comics:
		old_entry = old_entries_by_position.get(comic.position)
		if old_entry is None:
			warnings.append(f"{comic.path.name}: no old reading-order entry for position {comic.position:04d}; skipped")
			continue

		new_entry = new_entries_by_match_key.get(entry_match_key(old_entry))
		if new_entry is None:
			warnings.append(
				f"{comic.path.name}: no new reading-order entry for {old_entry.run} volume {old_entry.volume} #{old_entry.issue_label}; skipped"
			)
			continue

		items.append(_migration_item(comic, new_entry.position))

	return items, warnings


def _plan_from_filenames(
	destination_comics: tuple[DestinationComic, ...],
	new_entries: tuple[ReadingOrderEntry, ...],
	config: OrganizerConfig | None,
) -> tuple[list[MigrationPlanItem], list[str]]:
	entries_by_decoded_key = _decoded_entry_index(new_entries, config)
	items: list[MigrationPlanItem] = []
	warnings: list[str] = []

	for comic in destination_comics:
		key = _decoded_key(comic.title, comic.issue_label)
		matching_entries = entries_by_decoded_key.get(key, ())
		if not matching_entries:
			warnings.append(f"{comic.path.name}: no new reading-order entry matching {comic.title} #{comic.issue_label}; skipped")
			continue
		if len(matching_entries) > 1:
			positions = ", ".join(f"{entry.position:04d}/v{entry.volume}" for entry in matching_entries)
			warnings.append(f"{comic.path.name}: ambiguous new reading-order matches ({positions}); use --old-reading-order; skipped")
			continue

		items.append(_migration_item(comic, matching_entries[0].position))

	return items, warnings


def _unique_entry_index(entries: tuple[ReadingOrderEntry, ...]) -> dict[tuple[str, str, str], ReadingOrderEntry]:
	index: dict[tuple[str, str, str], ReadingOrderEntry] = {}
	for entry in entries:
		key = entry_match_key(entry)
		if key in index:
			raise MigrationError(f"New reading-order JSON has duplicate entry: {entry.run} volume {entry.volume} #{entry.issue_label}")
		index[key] = entry

	return index


def _decoded_entry_index(
	entries: tuple[ReadingOrderEntry, ...],
	config: OrganizerConfig | None,
) -> dict[tuple[str, str], tuple[ReadingOrderEntry, ...]]:
	aliases = _output_name_aliases(config)
	index: dict[tuple[str, str], list[ReadingOrderEntry]] = {}
	for entry in entries:
		names = {entry.run, *aliases.get((entry.run.casefold(), entry.volume), set())}
		for name in names:
			index.setdefault(_decoded_key(name, entry.issue_label), []).append(entry)

	return {key: tuple(value) for key, value in index.items()}


def _output_name_aliases(config: OrganizerConfig | None) -> dict[tuple[str, str], set[str]]:
	aliases: dict[tuple[str, str], set[str]] = {}
	if config is None:
		return aliases

	for source_folder in config.source_folders:
		aliases.setdefault((source_folder.run.casefold(), source_folder.volume), set()).add(source_folder.output_name)
		aliases.setdefault((source_folder.annual_run.casefold(), source_folder.annual_volume), set()).add(source_folder.annual_output_name)

	return aliases


def _decoded_key(title: str, issue_label: str) -> tuple[str, str]:
	return (title.casefold(), comparable_issue_number(issue_label))


def _migration_item(comic: DestinationComic, new_position: int) -> MigrationPlanItem:
	return MigrationPlanItem(
		source_path=comic.path,
		destination_path=comic.path.with_name(f"{new_position:04d} - {comic.title} #{comic.issue_label}.cbz"),
		old_position=comic.position,
		new_position=new_position,
	)


def _validate_plan(folder: Path, items: list[MigrationPlanItem]) -> None:
	target_positions: set[int] = set()
	target_names: set[str] = set()
	source_names = {item.source_path.name.casefold() for item in items}
	existing_names = {path.name.casefold() for path in folder.iterdir() if path.is_file()}

	for item in items:
		if item.new_position in target_positions:
			raise MigrationError(f"Migration would create duplicate target position: {item.new_position:04d}")
		target_positions.add(item.new_position)

		target_name = item.destination_path.name.casefold()
		if target_name in target_names:
			raise MigrationError(f"Migration would create duplicate target filename: {item.destination_path.name}")
		if target_name in existing_names and target_name not in source_names:
			raise MigrationError(f"Target already exists outside migration plan: {item.destination_path.name}")
		target_names.add(target_name)


if __name__ == "__main__":
	raise SystemExit(main())
