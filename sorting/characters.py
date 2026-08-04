"""Parse per-project character lists and report duplicate character claims."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import ConfigError


MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
MARKDOWN_STYLE_RE = re.compile(r"[*_`]")
SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")


@dataclass(frozen=True)
class CharacterClaim:
	name: str
	keys: tuple[str, ...]
	path: Path
	line_number: int


@dataclass(frozen=True)
class DuplicateCharacterClaim:
	key: str
	claims: tuple[CharacterClaim, ...]


def read_character_claims(path: str | Path) -> tuple[CharacterClaim, ...]:
	"""Read character names from Markdown tables and simple bullet lists."""
	character_list_path = Path(path)
	try:
		lines = character_list_path.read_text(encoding="utf-8-sig").splitlines()
	except FileNotFoundError as exc:
		raise ValueError(f"Character list does not exist: {character_list_path}") from exc

	claims: list[CharacterClaim] = []
	for line_number, line in enumerate(lines, start=1):
		name = character_name_from_markdown_line(line)
		if name is None:
			continue

		keys = character_keys(name)
		if not keys:
			continue

		claims.append(
			CharacterClaim(
				name=name,
				keys=keys,
				path=character_list_path,
				line_number=line_number,
			)
		)

	return tuple(claims)


def character_name_from_markdown_line(line: str) -> str | None:
	"""Extract the first cell from a character Markdown table or bullet row."""
	stripped = line.strip()
	if not stripped:
		return None

	if stripped.startswith("|"):
		cells = [clean_markdown_text(cell) for cell in stripped.strip("|").split("|")]
		if not cells:
			return None
		first_cell = cells[0]
		if not first_cell:
			return None
		if first_cell.casefold() == "character":
			return None
		if SEPARATOR_CELL_RE.match(first_cell):
			return None
		return first_cell

	if stripped.startswith(("- ", "* ")):
		name = clean_markdown_text(stripped[2:])
		return name or None

	return None


def character_keys(name: str) -> tuple[str, ...]:
	"""Return normalized duplicate-detection keys for a character name."""
	keys: list[str] = []
	for value in (name, *split_aliases(name)):
		key = normalize_character_key(value)
		if key and key not in keys:
			keys.append(key)
	return tuple(keys)


def split_aliases(name: str) -> tuple[str, ...]:
	"""Split common alias forms without trying to infer hidden business intent."""
	aliases: list[str] = []
	for part in re.split(r"\s+/\s+", name):
		part = part.strip()
		if not part:
			continue
		aliases.append(part)
		for parenthetical in re.findall(r"\(([^)]+)\)", part):
			if parenthetical.strip():
				aliases.append(parenthetical.strip())
		without_parenthetical = re.sub(r"\s*\([^)]*\)", "", part).strip()
		if without_parenthetical and without_parenthetical != part:
			aliases.append(without_parenthetical)
	return tuple(aliases)


def normalize_character_key(value: str) -> str:
	"""Normalize a character label for conservative cross-list duplicate checks."""
	text = clean_markdown_text(value)
	text = re.sub(r"\([^)]*\)", " ", text)
	text = re.sub(r"&[a-zA-Z]+;", " ", text)
	text = re.sub(r"[^A-Za-z0-9]+", " ", text)
	return re.sub(r"\s+", " ", text).strip().casefold()


def clean_markdown_text(value: str) -> str:
	"""Remove Markdown formatting from a table cell while preserving visible text."""
	text = MARKDOWN_LINK_RE.sub(r"\1", value)
	text = MARKDOWN_STYLE_RE.sub("", text)
	return re.sub(r"\s+", " ", text).strip()


def find_duplicate_claims(claims: tuple[CharacterClaim, ...]) -> tuple[DuplicateCharacterClaim, ...]:
	"""Find normalized character keys claimed by more than one list file."""
	claims_by_key: dict[str, list[CharacterClaim]] = {}
	for claim in claims:
		for key in claim.keys:
			claims_by_key.setdefault(key, []).append(claim)

	duplicates: list[DuplicateCharacterClaim] = []
	for key, key_claims in claims_by_key.items():
		unique_claims = tuple(dict.fromkeys(key_claims))
		unique_paths = {claim.path for claim in unique_claims}
		if len(unique_paths) > 1:
			duplicates.append(DuplicateCharacterClaim(key=key, claims=unique_claims))

	return tuple(sorted(duplicates, key=lambda duplicate: duplicate.key))


def discover_character_list_paths(root: str | Path) -> tuple[Path, ...]:
	"""Find Markdown character lists under the configured list root."""
	root_path = Path(root)
	if not root_path.exists():
		return ()
	if root_path.is_file():
		return (root_path,)
	project_paths = list(root_path.glob("*/characters.md"))
	paths = project_paths or list(root_path.glob("*.md"))
	return tuple(sorted(paths, key=lambda path: str(path).casefold()))


def build_duplicate_report(paths: tuple[Path, ...]) -> tuple[list[str], bool]:
	"""Build terminal lines for duplicate claims across character-list files."""
	claims: list[CharacterClaim] = []
	for path in paths:
		claims.extend(read_character_claims(path))

	duplicates = find_duplicate_claims(tuple(claims))
	lines = [
		f"Character lists checked: {len(paths)}",
		f"Character claims found: {len(claims)}",
		"",
		"Duplicate character claims:",
	]
	if not duplicates:
		lines.append("  (none)")
		return lines, False

	for duplicate in duplicates:
		lines.append(f"  {duplicate.key}")
		for claim in duplicate.claims:
			lines.append(f"    {claim.path}:{claim.line_number} - {claim.name}")

	return lines, True


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv)
	try:
		paths = selected_character_list_paths(args)
		lines, has_duplicates = build_duplicate_report(paths)
	except (ConfigError, ValueError) as exc:
		print(f"ERROR {exc}", file=sys.stderr)
		return 1

	for line in lines:
		print(line)
	return 1 if has_duplicates else 0


def selected_character_list_paths(args: argparse.Namespace) -> tuple[Path, ...]:
	"""Resolve character-list paths from a config, explicit file, or list root."""
	if args.config:
		return (character_list_path_from_config(args.config),)

	if args.path:
		return tuple(Path(path) for path in args.path)

	paths = discover_character_list_paths(args.root)
	if not paths:
		raise ValueError(f"No Markdown character lists found in: {args.root}")
	return paths


def character_list_path_from_config(config_path: str | Path) -> Path:
	"""Read only character_list_path so ownership checks work before DB setup."""
	path = Path(config_path)
	try:
		raw_config = json.loads(path.read_text(encoding="utf-8"))
	except FileNotFoundError as exc:
		raise ConfigError(f"Config file does not exist: {path}") from exc
	except json.JSONDecodeError as exc:
		raise ConfigError(f"Config file is not valid JSON: {path}: {exc}") from exc
	if not isinstance(raw_config, dict):
		raise ConfigError(f"Config file must contain a JSON object: {path}")

	value = raw_config.get("character_list_path", "characters.md")
	if not isinstance(value, str) or not value.strip():
		raise ValueError(f"Config field 'character_list_path' must be a non-empty string when provided: {path}")

	character_list_path = Path(value.strip())
	if character_list_path.is_absolute():
		return character_list_path
	parent = path.parent if str(path.parent) else Path(".")
	return parent / character_list_path


def parse_args(argv: list[str] | None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Check Markdown character lists for duplicate character claims."
	)
	parser.add_argument("--config", help="Organizer config with a character_list_path field.")
	parser.add_argument("--root", default="projects", help="Folder of project character lists.")
	parser.add_argument("--path", action="append", help="Specific character-list Markdown file. Repeatable.")
	return parser.parse_args(argv)


if __name__ == "__main__":
	raise SystemExit(main())
