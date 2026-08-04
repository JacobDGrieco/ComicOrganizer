"""Run organizer commands against a selected project config."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import reindex_output
from . import list_order
from . import missing_entries
from . import organizer
from .characters import main as characters_main
from .config import ConfigError, load_config
from .logging import default_log_path

PROJECTS_ROOT = Path("projects")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = selected_config_path(args)

    try:
        if args.command == "sort":
            command_args = ["--config", str(config_path)]
            if args.dry_run:
                command_args.append("--dry-run")
            return organizer.main(command_args)
        if args.command == "missing":
            return missing_entries.main(["--config", str(config_path)])
        if args.command == "list":
            return list_order.main(["--config", str(config_path)])
        if args.command == "reindex":
            command_args = ["--config", str(config_path)]
            if args.apply:
                command_args.append("--apply")
            return reindex_output.main(command_args)
        if args.command == "characters":
            return characters_main(["--config", str(config_path)])
        if args.command == "db-validate":
            return run_database_script(config_path, "db_validate.py")
        if args.command == "flatten":
            return run_flatten(config_path, apply=args.apply, paths=args.path)
        if args.command == "download":
            return run_downloader(config_path, headless=args.headless)
    except ConfigError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    print(f"ERROR unsupported command: {args.command}", file=sys.stderr)
    return 1


def selected_config_path(args: argparse.Namespace) -> Path:
    """Resolve an explicit config or a named project profile."""
    if args.config:
        return Path(args.config)
    if args.project:
        return PROJECTS_ROOT / args.project / "config.json"
    return Path("config.json")


def run_database_script(config_path: Path, script_name: str) -> int:
    """Run a database helper against the selected config's SQLite path."""
    config = load_config(config_path)
    command = [
        sys.executable,
        str(Path("scripts") / script_name),
        "--db",
        str(config.reading_order_path),
    ]
    return subprocess.run(command, check=False).returncode


def run_flatten(config_path: Path, *, apply: bool, paths: list[str] | None) -> int:
    """Flatten configured source folders while writing the selected project's log."""
    config = load_config(config_path)
    flatten_paths = paths or [
        str(source_folder.path) for source_folder in config.source_folders
    ]
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path("scripts") / "flatten-cbz.ps1"),
        *flatten_paths,
        "-LogPath",
        str(default_log_path(config_path, "flatten-cbz.log")),
    ]
    if apply:
        command.append("-Apply")
    return subprocess.run(command, check=False).returncode


def run_downloader(config_path: Path, *, headless: bool) -> int:
    """Run the downloader with optional per-project URL and output paths."""
    raw_config = read_raw_config(config_path)
    config_folder = config_path.parent if str(config_path.parent) else Path(".")
    urls_path = optional_config_path(raw_config, config_folder, "download_urls_path")
    output_folder = optional_config_path(
        raw_config, config_folder, "download_output_folder"
    )
    if output_folder is not None and urls_path is None:
        urls_path = default_download_urls_path(config_path)

    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path("downloader") / "run.ps1"),
    ]
    if urls_path is not None:
        command.append(str(urls_path))
    if output_folder is not None:
        command.append(str(output_folder))
    if headless:
        command.append("-Headless")
    command.extend(["-LogPath", str(default_log_path(config_path, "downloader.log"))])
    return subprocess.run(command, check=False).returncode


def default_download_urls_path(config_path: Path) -> Path:
    """Return the URL CSV path needed when only an output folder is configured."""
    config_folder = config_path.parent if str(config_path.parent) else Path(".")
    project_urls_path = config_folder / "downloader" / "urls.csv"
    if project_urls_path.exists():
        return project_urls_path
    return Path("downloader") / "urls.csv"


def read_raw_config(config_path: Path) -> dict[str, object]:
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file does not exist: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Config file is not valid JSON: {config_path}: {exc}"
        ) from exc
    if not isinstance(raw_config, dict):
        raise ConfigError(f"Config file must contain a JSON object: {config_path}")
    return raw_config


def optional_config_path(
    raw_config: dict[str, object], config_folder: Path, key: str
) -> Path | None:
    value = raw_config.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"Config field '{key}' must be a non-empty string when provided"
        )
    path = Path(value.strip())
    return path if path.is_absolute() else config_folder / path


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ComicOrganizer commands for one project profile."
    )
    parser.add_argument(
        "command",
        choices=(
            "sort",
            "missing",
            "list",
            "reindex",
            "flatten",
            "download",
            "characters",
            "db-validate",
        ),
    )
    parser.add_argument(
        "--project", help="Project folder under projects/, such as spider-man or x-men."
    )
    parser.add_argument("--config", help="Explicit config path. Overrides --project.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry-run sort operations."
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply reindex or flatten operations."
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run downloader browser in hidden mode."
    )
    parser.add_argument(
        "--path",
        action="append",
        help="Flatten this path instead of configured source folders.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
