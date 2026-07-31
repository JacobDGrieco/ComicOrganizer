"""Shared helpers for mirroring command output into project log files."""

from __future__ import annotations

from pathlib import Path


def default_log_path(config_path: str | Path, filename: str) -> Path:
	"""Return the default logs folder next to the selected config file."""
	path = Path(config_path)
	parent = path.parent if str(path.parent) else Path(".")
	return parent / "logs" / filename


def write_log(log_path: Path, lines: list[str]) -> None:
	"""Replace a log file with the same lines printed to the terminal."""
	log_path.parent.mkdir(parents=True, exist_ok=True)
	log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_log(log_path: Path, lines: list[str]) -> None:
	"""Append additional terminal lines to an existing log file."""
	log_path.parent.mkdir(parents=True, exist_ok=True)
	with log_path.open("a", encoding="utf-8") as log_file:
		log_file.write("\n".join(lines) + "\n")
