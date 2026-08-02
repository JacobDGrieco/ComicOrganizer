"""Load and validate organizer configuration before any file operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .issue_numbers import comparable_issue_number, normalize_issue_label, normalize_volume_label
from .logging import default_log_path
from .models import OrganizerConfig, SourceFolderConfig


class ConfigError(ValueError):
	pass


def load_config(config_path: str | Path) -> OrganizerConfig:
	path = Path(config_path)
	try:
		raw_config = json.loads(path.read_text(encoding="utf-8"))
	except FileNotFoundError as exc:
		raise ConfigError(f"Config file does not exist: {path}") from exc
	except json.JSONDecodeError as exc:
		raise ConfigError(f"Config file is not valid JSON: {path}: {exc}") from exc

	return _validate_config(raw_config, path)


def _validate_config(raw_config: Any, config_path: Path) -> OrganizerConfig:
	if not isinstance(raw_config, dict):
		raise ConfigError(f"Config file must contain a JSON object: {config_path}")

	reading_order_path = _required_path(raw_config, "reading_order_path")
	destination_folder = _required_path(raw_config, "destination_folder")
	log_path = _optional_path(raw_config, "log_path") or default_log_path(config_path, "comic-organizer.log")
	source_folders = _source_folders(raw_config.get("source_folders"))
	issue_overrides = _issue_overrides(raw_config.get("issue_overrides", {}))

	_require_file(reading_order_path, "Reading-order source")
	_require_directory(destination_folder, "Destination folder")

	return OrganizerConfig(
		reading_order_path=reading_order_path,
		destination_folder=destination_folder,
		log_path=log_path,
		source_folders=tuple(source_folders),
		issue_overrides=issue_overrides,
	)


def _required_string(raw_config: dict[str, Any], key: str) -> str:
	value = raw_config.get(key)
	if not isinstance(value, str) or not value.strip():
		raise ConfigError(f"Config field '{key}' must be a non-empty string")

	return value.strip()


def _required_path(raw_config: dict[str, Any], key: str) -> Path:
	return Path(_required_string(raw_config, key))


def _optional_path(raw_config: dict[str, Any], key: str) -> Path | None:
	value = raw_config.get(key)
	if value is None:
		return None
	if not isinstance(value, str) or not value.strip():
		raise ConfigError(f"Config field '{key}' must be a non-empty string when provided")
	return Path(value.strip())


def _source_folders(value: Any) -> list[SourceFolderConfig]:
	if not isinstance(value, list) or not value:
		raise ConfigError("Config field 'source_folders' must be a non-empty list")

	source_folders: list[SourceFolderConfig] = []
	for index, raw_source_folder in enumerate(value, start=1):
		if not isinstance(raw_source_folder, dict):
			raise ConfigError(f"source_folders[{index}] must be an object")

		path = raw_source_folder.get("path")
		run = raw_source_folder.get("run")
		volume = raw_source_folder.get("volume")
		annual_run = raw_source_folder.get("annual_run", f"{run} Annual" if isinstance(run, str) else "")
		annual_volume = raw_source_folder.get("annual_volume", volume)
		annual_start_year = raw_source_folder.get("annual_start_year", "")
		special_run = raw_source_folder.get("special_run", f"{run} Special" if isinstance(run, str) else "")
		special_volume = raw_source_folder.get("special_volume", volume)
		issue_aliases = _issue_aliases(raw_source_folder.get("issue_aliases", {}), f"source_folders[{index}].issue_aliases")
		source_title_aliases = _string_list(
			raw_source_folder.get("source_title_aliases", ()),
			f"source_folders[{index}].source_title_aliases",
		)
		if not isinstance(path, str) or not path.strip():
			raise ConfigError(f"source_folders[{index}].path must be a non-empty string")
		if not isinstance(run, str) or not run.strip():
			raise ConfigError(f"source_folders[{index}].run must be a non-empty string")
		volume_label = normalize_volume_label(volume)
		if not volume_label:
			raise ConfigError(f"source_folders[{index}].volume must be a non-empty value")
		if not isinstance(annual_run, str) or not annual_run.strip():
			raise ConfigError(f"source_folders[{index}].annual_run must be a non-empty string")
		annual_volume_label = normalize_volume_label(annual_volume)
		if not annual_volume_label:
			raise ConfigError(f"source_folders[{index}].annual_volume must be a non-empty value")
		if annual_start_year is not None and not isinstance(annual_start_year, str):
			raise ConfigError(f"source_folders[{index}].annual_start_year must be a string")
		if not isinstance(special_run, str) or not special_run.strip():
			raise ConfigError(f"source_folders[{index}].special_run must be a non-empty string")
		special_volume_label = normalize_volume_label(special_volume)
		if not special_volume_label:
			raise ConfigError(f"source_folders[{index}].special_volume must be a non-empty value")

		source_folders.append(
			SourceFolderConfig(
				path=Path(path),
				run=run.strip(),
				volume=volume_label,
				annual_run=annual_run.strip(),
				annual_volume=annual_volume_label,
				annual_start_year=str(annual_start_year or "").strip(),
				special_run=special_run.strip(),
				special_volume=special_volume_label,
				issue_aliases=issue_aliases,
				source_title_aliases=source_title_aliases,
			)
		)

	return source_folders


def _string_list(value: Any, label: str) -> tuple[str, ...]:
	if not isinstance(value, (list, tuple)):
		raise ConfigError(f"Config field '{label}' must be a list")

	items: list[str] = []
	for index, item in enumerate(value, start=1):
		if not isinstance(item, str) or not item.strip():
			raise ConfigError(f"{label}[{index}] must be a non-empty string")
		items.append(item.strip())

	return tuple(items)


def _issue_aliases(value: Any, label: str = "issue_aliases") -> dict[str, str]:
	if not isinstance(value, dict):
		raise ConfigError(f"Config field '{label}' must be an object")

	aliases: dict[str, str] = {}
	for source_issue, database_issue in value.items():
		if not isinstance(source_issue, str) or not source_issue.strip():
			raise ConfigError(f"{label} keys must be non-empty strings")
		if not isinstance(database_issue, str) or not database_issue.strip():
			raise ConfigError(f"{label}['{source_issue}'] must be a non-empty string")
		aliases[comparable_issue_number(source_issue)] = normalize_issue_label(database_issue)

	return aliases


def _issue_overrides(value: Any) -> dict[str, dict[str, str]]:
	if not isinstance(value, dict):
		raise ConfigError("Config field 'issue_overrides' must be an object")

	overrides: dict[str, dict[str, str]] = {}
	for run, run_overrides in value.items():
		if not isinstance(run, str) or not run.strip():
			raise ConfigError("issue_overrides keys must be non-empty run names")
		if not isinstance(run_overrides, dict):
			raise ConfigError(f"issue_overrides['{run}'] must be an object")

		overrides[run.strip()] = {}
		for sequence_number, issue_label in run_overrides.items():
			if not isinstance(sequence_number, str) or not sequence_number.strip():
				raise ConfigError(f"issue_overrides['{run}'] keys must be non-empty strings")
			if not isinstance(issue_label, str) or not issue_label.strip():
				raise ConfigError(f"issue_overrides['{run}']['{sequence_number}'] must be a non-empty string")
			overrides[run.strip()][sequence_number.strip()] = issue_label.strip()

	return overrides


def _require_file(path: Path, label: str) -> None:
	if not path.is_file():
		raise ConfigError(f"{label} does not exist or is not a file: {path}")


def _require_directory(path: Path, label: str) -> None:
	if not path.is_dir():
		raise ConfigError(f"{label} does not exist or is not a folder: {path}")
