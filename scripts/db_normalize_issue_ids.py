"""Normalize issue primary keys to the FANDOM-ISS namespace."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

from db_common import connect_database


@dataclass(frozen=True)
class IssueRow:
	id: str
	cand_id: str
	issue_number: str
	release_date: str


@dataclass(frozen=True)
class IssueMove:
	old_id: str
	target_id: str
	cand_id: str
	issue_number: str
	release_date: str


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
		description="Rename issue IDs to FANDOM-ISS-<CAND-ID>-<ISSUE>."
	)
	parser.add_argument("--db", default="projects/spider-man/database/database.db", help="SQLite database path.")
	parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
	return parser.parse_args()


def plan_moves(connection) -> list[IssueMove]:
	rows = fetch_issues(connection)
	targets: dict[str, IssueRow] = {}
	moves: list[IssueMove] = []
	for row in rows:
		target_id = stable_issue_id(row.cand_id, row.issue_number)
		existing = targets.get(target_id)
		if existing is not None and existing.id != row.id:
			raise RuntimeError(
				f"Target issue ID collision: {target_id} for {existing.id} and {row.id}"
			)
		targets[target_id] = row
		if row.id != target_id:
			moves.append(
				IssueMove(
					old_id=row.id,
					target_id=target_id,
					cand_id=row.cand_id,
					issue_number=row.issue_number,
					release_date=row.release_date,
				)
			)
	return moves


def fetch_issues(connection) -> list[IssueRow]:
	rows = connection.execute(
		"""
		SELECT id, cand_id, issue_number, release_date
		FROM issues
		ORDER BY release_date, cand_id, CAST(issue_number AS REAL), issue_number, id
		"""
	).fetchall()
	return [
		IssueRow(
			id=row["id"],
			cand_id=row["cand_id"],
			issue_number=row["issue_number"],
			release_date=row["release_date"],
		)
		for row in rows
	]


def apply_moves(connection, moves: list[IssueMove]) -> None:
	for move in moves:
		connection.execute(
			"UPDATE issues SET id = ? WHERE id = ?",
			(move.target_id, move.old_id),
		)


def stable_issue_id(cand_id: str, issue_number: str) -> str:
	return f"FANDOM-ISS-{slugify(cand_id)}-{slugify_issue_number(issue_number)}"


def slugify_issue_number(issue_number: str) -> str:
	value = issue_number.strip().upper()
	value = value.replace("-", "NEG-")
	value = value.replace("/", "-SLASH-")
	value = value.replace(".", "-POINT-")
	return slugify(value)


def slugify(value: str) -> str:
	slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
	return slug or "UNKNOWN"


def print_summary(moves: list[IssueMove], *, dry_run: bool) -> None:
	mode = "Dry run" if dry_run else "Normalize"
	print(f"{mode}: issue IDs to rename: {len(moves)}")
	for move in moves[:20]:
		print(
			f"{move.old_id} -> {move.target_id} "
			f"({move.cand_id} #{move.issue_number}, {move.release_date})"
		)


if __name__ == "__main__":
	raise SystemExit(main())
