"""Move matched comics into the destination folder with canonical filenames."""

from __future__ import annotations

import shutil
from pathlib import Path
import re

from colorama import Fore, Style, init

from .models import MatchedComic, MoveResult, ProcessSummary


init(autoreset=True)


_POSITION_PREFIX_RE = re.compile(r"^(?P<position>\d{4}) - ")


def find_existing_positions(destination_folder: str | Path) -> frozenset[int]:
	"""Return destination positions that already have a prefixed file."""
	destination = Path(destination_folder)
	positions: set[int] = set()
	for path in destination.iterdir():
		if not path.is_file():
			continue

		match = _POSITION_PREFIX_RE.match(path.name)
		if match:
			positions.add(int(match.group("position")))

	return frozenset(positions)


def process_matches(
	matches: tuple[MatchedComic, ...],
	destination_folder: str | Path,
	dry_run: bool = False,
	verbose: bool = True,
) -> ProcessSummary:
	destination = Path(destination_folder)
	results: list[MoveResult] = []

	for match in sorted(matches, key=lambda current_match: current_match.position):
		destination_path = destination / match.canonical_name
		if _position_exists(destination, match.position):
			if verbose:
				_print_skip(match)
			results.append(MoveResult(match=match, action="skipped", destination_path=destination_path))
			continue

		if dry_run:
			if verbose:
				_print_move(match, destination_path, dry_run=True)
			results.append(MoveResult(match=match, action="dry_run", destination_path=destination_path))
			continue

		try:
			shutil.move(str(match.source_path), str(destination_path))
		except OSError as exc:
			if verbose:
				_print_failure(match, exc)
			results.append(MoveResult(match=match, action="failed", destination_path=destination_path, error=str(exc)))
			continue

		if verbose:
			_print_move(match, destination_path, dry_run=False)
		results.append(MoveResult(match=match, action="moved", destination_path=destination_path))

	return ProcessSummary(
		moved=sum(1 for result in results if result.action == "moved"),
		skipped=sum(1 for result in results if result.action == "skipped"),
		failed=sum(1 for result in results if result.action == "failed"),
		results=tuple(results),
	)


def _position_exists(destination_folder: Path, position: int) -> bool:
	return position in find_existing_positions(destination_folder)


def _print_move(match: MatchedComic, destination_path: Path, dry_run: bool) -> None:
	action = "would move" if dry_run else "moved"
	print(f"{Fore.GREEN}OK{Style.RESET_ALL} {action}: {match.source_path} -> {destination_path}")


def _print_skip(match: MatchedComic) -> None:
	print(f"{Fore.CYAN}SKIP{Style.RESET_ALL} already present: {match.position:04d} - {match.run} #{match.issue_label}")


def _print_failure(match: MatchedComic, error: OSError) -> None:
	print(f"{Fore.RED}FAIL{Style.RESET_ALL} move failed: {match.source_path}: {error}")
