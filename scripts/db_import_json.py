"""Import the current JSON research files into the local SQLite database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from db_common import connect_database, project_root


def main() -> int:
    args = parse_args()
    root = project_root()
    data_dir = root / "data"

    with connect_database(args.db) as connection:
        import_universes(connection, read_records(data_dir / "universes.json"))
        import_sources(connection, read_records(data_dir / "sources.json"))
        import_runs(connection, read_records(data_dir / "series.json"))
        import_arcs(connection, read_records(data_dir / "storyArcs.json"))
        import_issues(connection, read_records(data_dir / "issues.json"))
        import_reviews(connection, read_records(data_dir / "review.json"))

    print(f"Imported JSON research data into: {args.db}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import JSON research data into SQLite."
    )
    parser.add_argument("--db", default="database.db", help="SQLite database path.")
    return parser.parse_args()


def read_records(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")).get("records", [])


def import_universes(connection, records: list[dict[str, Any]]) -> None:
    for record in records:
        connection.execute(
            """
			INSERT INTO universes (id, name, display_name, description)
			VALUES (?, ?, ?, ?)
			ON CONFLICT(id) DO UPDATE SET
				name = excluded.name,
				display_name = excluded.display_name,
				description = excluded.description
			""",
            (
                record["id"],
                record["name"],
                record.get("displayName"),
                record.get("description"),
            ),
        )


def import_sources(connection, records: list[dict[str, Any]]) -> None:
    for record in records:
        connection.execute(
            """
			INSERT INTO sources (id, name, url, source_type, accessed_date, notes)
			VALUES (?, ?, ?, ?, ?, ?)
			ON CONFLICT(id) DO UPDATE SET
				name = excluded.name,
				url = excluded.url,
				source_type = excluded.source_type,
				accessed_date = excluded.accessed_date,
				notes = excluded.notes
			""",
            (
                record["id"],
                record["name"],
                record["url"],
                record.get("sourceType"),
                record.get("accessedDate"),
                record.get("notes"),
            ),
        )


def import_runs(connection, records: list[dict[str, Any]]) -> None:
    for record in records:
        volume = str(record.get("volume") or "1")
        connection.execute(
            """
			INSERT INTO comic_runs (
				id, title, sort_title, volume, display_volume, publication_type, status, publisher,
				universe_id, start_date, start_date_precision, end_date, end_date_precision, numbering_summary
			)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(id) DO UPDATE SET
				title = excluded.title,
				sort_title = excluded.sort_title,
				volume = excluded.volume,
				display_volume = excluded.display_volume,
				publication_type = excluded.publication_type,
				status = excluded.status,
				publisher = excluded.publisher,
				universe_id = excluded.universe_id,
				start_date = excluded.start_date,
				start_date_precision = excluded.start_date_precision,
				end_date = excluded.end_date,
				end_date_precision = excluded.end_date_precision,
				numbering_summary = excluded.numbering_summary
			""",
            (
                record["id"],
                record["title"],
                record.get("sortTitle"),
                volume,
                record.get("displayVolume"),
                record.get("publicationType"),
                record.get("status"),
                record.get("publisher"),
                record["continuityId"],
                record["startDate"],
                record.get("startDatePrecision", "unknown"),
                record.get("endDate"),
                record.get("endDatePrecision", "unknown"),
                record.get("numberingSummary"),
            ),
        )
        insert_characters(connection, record.get("leadCharacterIds", []))
        for character_id in record.get("leadCharacterIds", []):
            connection.execute(
                "INSERT OR IGNORE INTO comic_run_characters (run_id, character_id) VALUES (?, ?)",
                (record["id"], character_id),
            )
        for source_id in record.get("sourceIds", []):
            connection.execute(
                "INSERT OR IGNORE INTO run_sources (run_id, source_id) VALUES (?, ?)",
                (record["id"], source_id),
            )


def import_arcs(connection, records: list[dict[str, Any]]) -> None:
    for record in records:
        connection.execute(
            """
			INSERT INTO story_arcs (
				id, title, universe_id, start_date, start_date_precision, end_date, end_date_precision
			)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(id) DO UPDATE SET
				title = excluded.title,
				universe_id = excluded.universe_id,
				start_date = excluded.start_date,
				start_date_precision = excluded.start_date_precision,
				end_date = excluded.end_date,
				end_date_precision = excluded.end_date_precision
			""",
            (
                record["id"],
                record["title"],
                record["continuityId"],
                record["startDate"],
                record.get("startDatePrecision", "unknown"),
                record.get("endDate"),
                record.get("endDatePrecision", "unknown"),
            ),
        )
        for source_id in record.get("sourceIds", []):
            connection.execute(
                "INSERT OR IGNORE INTO story_arc_sources (story_arc_id, source_id) VALUES (?, ?)",
                (record["id"], source_id),
            )


def import_issues(connection, records: list[dict[str, Any]]) -> None:
    for record in records:
        story_arc_id = first(record.get("storyArcIds", []))
        if story_arc_id is None:
            raise ValueError(f"Issue has no story arc: {record['id']}")
        connection.execute(
            """
			INSERT INTO issues (
				id, run_id, issue_number, release_date, release_date_precision, universe_id, story_arc_id
			)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(id) DO UPDATE SET
				run_id = excluded.run_id,
				issue_number = excluded.issue_number,
				release_date = excluded.release_date,
				release_date_precision = excluded.release_date_precision,
				universe_id = excluded.universe_id,
				story_arc_id = excluded.story_arc_id
			""",
            (
                record["id"],
                record["seriesId"],
                record["issueNumber"],
                record["releaseDate"],
                record.get("releaseDatePrecision", "unknown"),
                record["continuityId"],
                story_arc_id,
            ),
        )
        insert_characters(connection, record.get("leadCharacterIds", []))
        for character_id in record.get("leadCharacterIds", []):
            connection.execute(
                "INSERT OR IGNORE INTO issue_characters (issue_id, character_id) VALUES (?, ?)",
                (record["id"], character_id),
            )
        for source_id in record.get("sourceIds", []):
            connection.execute(
                "INSERT OR IGNORE INTO issue_sources (issue_id, source_id) VALUES (?, ?)",
                (record["id"], source_id),
            )


def import_reviews(connection, records: list[dict[str, Any]]) -> None:
    for record in records:
        connection.execute(
            """
			INSERT INTO review_items (id, entity_type, entity_id, category, question, status, priority, notes)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(id) DO UPDATE SET
				entity_type = excluded.entity_type,
				entity_id = excluded.entity_id,
				category = excluded.category,
				question = excluded.question,
				status = excluded.status,
				priority = excluded.priority,
				notes = excluded.notes
			""",
            (
                record["id"],
                record["entityType"],
                record.get("entityId"),
                record["category"],
                record["question"],
                record["status"],
                record["priority"],
                json.dumps(record.get("notes", []), ensure_ascii=True),
            ),
        )


def insert_characters(connection, character_ids: list[str]) -> None:
    for character_id in character_ids:
        connection.execute(
            "INSERT OR IGNORE INTO characters (id, name) VALUES (?, ?)",
            (character_id, character_name(character_id)),
        )


def character_name(character_id: str) -> str:
    name = character_id.removeprefix("CHAR-").replace("-", " ").title()
    return name.replace("O'Hara", "O'Hara")


def first(values: list[str]) -> str | None:
    return values[0] if values else None


if __name__ == "__main__":
    raise SystemExit(main())
