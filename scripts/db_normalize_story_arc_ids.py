"""Normalize legacy placeholder story-arc IDs in the simplified SQLite catalog."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

from db_common import connect_database

LEGACY_PREFIXES = ("ARC-", "GCD-ARC-", "MM-ARC-", "FANDOM-ARC-")
CANONICAL_PREFIXES = ("FANDOM-EVENT-", "FANDOM-STORY-")


@dataclass(frozen=True)
class StoryArcRow:
	id: str
	title: str
	start_date: str
	start_date_precision: str
	end_date: str | None
	end_date_precision: str
	issue_count: int


@dataclass(frozen=True)
class StoryArcMove:
	old_id: str
	target_id: str
	title: str
	issue_count: int
	action: str


def main() -> int:
	args = parse_args()
	with connect_database(args.db) as connection:
		moves = plan_moves(connection)
		if args.dry_run:
			print_summary(moves, dry_run=True)
			return 0
		apply_moves(connection, moves)
	print_summary(moves, dry_run=False)
	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Rename old ARC/GCD-ARC/MM-ARC/FANDOM-ARC IDs to the current namespace."
	)
	parser.add_argument("--db", default="projects/spider-man/database/database.db", help="SQLite database path.")
	parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
	return parser.parse_args()


def plan_moves(connection) -> list[StoryArcMove]:
	legacy_arcs = fetch_legacy_arcs(connection)
	canonical_by_title = fetch_canonical_title_map(connection)
	reserved_ids = fetch_non_legacy_ids(connection)
	moves: list[StoryArcMove] = []

	for arc in legacy_arcs:
		canonical_targets = canonical_by_title.get(normalize_title_key(arc.title), [])
		if len(canonical_targets) == 1:
			target_id = canonical_targets[0]
			action = "merge-canonical"
		else:
			target_id = next_local_arc_id(arc, reserved_ids)
			action = "rename-local"
		reserved_ids.add(target_id)
		moves.append(
			StoryArcMove(
				old_id=arc.id,
				target_id=target_id,
				title=arc.title,
				issue_count=arc.issue_count,
				action=action,
			)
		)

	return moves


def fetch_legacy_arcs(connection) -> list[StoryArcRow]:
	where_clause = " OR ".join("story_arcs.id LIKE ?" for _ in LEGACY_PREFIXES)
	rows = connection.execute(
		f"""
		SELECT
			story_arcs.id,
			story_arcs.title,
			story_arcs.start_date,
			story_arcs.start_date_precision,
			story_arcs.end_date,
			story_arcs.end_date_precision,
			COUNT(issues.id) AS issue_count
		FROM story_arcs
		LEFT JOIN issues ON issues.story_arc_id = story_arcs.id
		WHERE {where_clause}
		GROUP BY story_arcs.id
		ORDER BY story_arcs.start_date, story_arcs.title, story_arcs.id
		""",
		[prefix + "%" for prefix in LEGACY_PREFIXES],
	).fetchall()
	return [
		StoryArcRow(
			id=row["id"],
			title=row["title"],
			start_date=row["start_date"],
			start_date_precision=row["start_date_precision"],
			end_date=row["end_date"],
			end_date_precision=row["end_date_precision"],
			issue_count=row["issue_count"],
		)
		for row in rows
	]


def fetch_canonical_title_map(connection) -> dict[str, list[str]]:
	where_clause = " OR ".join("id LIKE ?" for _ in CANONICAL_PREFIXES)
	rows = connection.execute(
		f"""
		SELECT id, title
		FROM story_arcs
		WHERE {where_clause}
		ORDER BY id
		""",
		[prefix + "%" for prefix in CANONICAL_PREFIXES],
	).fetchall()
	canonical_by_title: dict[str, list[str]] = {}
	for row in rows:
		canonical_by_title.setdefault(normalize_title_key(row["title"]), []).append(row["id"])
	return canonical_by_title


def fetch_non_legacy_ids(connection) -> set[str]:
	where_clause = " AND ".join("id NOT LIKE ?" for _ in LEGACY_PREFIXES)
	rows = connection.execute(
		f"SELECT id FROM story_arcs WHERE {where_clause}",
		[prefix + "%" for prefix in LEGACY_PREFIXES],
	).fetchall()
	return {row["id"] for row in rows}


def next_local_arc_id(arc: StoryArcRow, reserved_ids: set[str]) -> str:
	base = f"LOCAL-ARC-{slugify(arc.title)}"
	candidates = [
		base,
		f"{base}-{slugify(arc.start_date)}",
		f"{base}-{slugify(arc.start_date)}-{slugify(arc.id)}",
	]
	for candidate in candidates:
		if candidate not in reserved_ids:
			return candidate
	raise RuntimeError(f"Could not create a unique LOCAL-ARC id for {arc.id}.")


def apply_moves(connection, moves: list[StoryArcMove]) -> None:
	for move in moves:
		if move.old_id == move.target_id:
			continue
		if story_arc_exists(connection, move.target_id):
			update_issue_references(connection, move)
			delete_story_arc(connection, move.old_id)
			continue
		connection.execute(
			"""
			INSERT INTO story_arcs (
				id, title, start_date, start_date_precision, end_date, end_date_precision
			)
			SELECT
				?, title, start_date, start_date_precision, end_date, end_date_precision
			FROM story_arcs
			WHERE id = ?
			""",
			(move.target_id, move.old_id),
		)
		update_issue_references(connection, move)
		delete_story_arc(connection, move.old_id)


def story_arc_exists(connection, story_arc_id: str) -> bool:
	row = connection.execute(
		"SELECT 1 FROM story_arcs WHERE id = ?",
		(story_arc_id,),
	).fetchone()
	return row is not None


def update_issue_references(connection, move: StoryArcMove) -> None:
	connection.execute(
		"UPDATE issues SET story_arc_id = ? WHERE story_arc_id = ?",
		(move.target_id, move.old_id),
	)


def delete_story_arc(connection, story_arc_id: str) -> None:
	connection.execute("DELETE FROM story_arcs WHERE id = ?", (story_arc_id,))


def normalize_title_key(title: str) -> str:
	return re.sub(r"\s+", " ", title.strip()).casefold()


def slugify(value: str) -> str:
	slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
	return slug or "UNKNOWN"


def print_summary(moves: list[StoryArcMove], *, dry_run: bool) -> None:
	mode = "Dry run" if dry_run else "Normalize"
	merge_count = sum(1 for move in moves if move.action == "merge-canonical")
	rename_count = sum(1 for move in moves if move.action == "rename-local")
	referenced_issue_count = sum(move.issue_count for move in moves)
	print(f"{mode}: legacy story arcs inspected: {len(moves)}")
	print(f"Canonical merges: {merge_count}")
	print(f"Local placeholder renames: {rename_count}")
	print(f"Issue references moved: {referenced_issue_count}")
	for move in moves[:20]:
		print(
			f"{move.old_id} -> {move.target_id} "
			f"({move.action}, issues={move.issue_count}, title={move.title})"
		)


if __name__ == "__main__":
	raise SystemExit(main())
