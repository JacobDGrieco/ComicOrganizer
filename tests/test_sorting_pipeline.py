from __future__ import annotations

import contextlib
import io
import json
import shutil
import sqlite3
import unittest
from pathlib import Path

from sorting.missing_entries import build_missing_entries_report, format_report
from sorting.models import ReadingOrderEntry
from sorting.organizer import main


class OrganizerPipelineTests(unittest.TestCase):
	def test_missing_entries_report_stops_at_last_existing_position(self) -> None:
		reading_order = tuple(
			ReadingOrderEntry(
				position=position,
				run="The Amazing Spider-Man",
				volume="1",
				issue_label=str(position),
				release_date=f"1963-01-{position:02d}",
			)
			for position in range(1, 7)
		)

		report = build_missing_entries_report(reading_order, frozenset({1, 3, 5}))
		lines = format_report(report)

		self.assertEqual(report.last_existing_position, 5)
		self.assertEqual([entry.position for entry in report.missing_entries], [2, 4])
		self.assertIn("Missing entries in range: 2", lines)
		self.assertIn("  00002 - The Amazing Spider-Man v1 #2 (1963-01-02)", lines)
		self.assertNotIn("00006", "\n".join(lines))

	def test_dry_run_matches_normalized_regular_and_annual_year_filenames(self) -> None:
		root = Path.cwd() / ".test-tmp" / "organizer-pipeline"
		shutil.rmtree(root, ignore_errors=True)
		try:
			root.mkdir(parents=True)
			database_path = root / "database.db"
			source_folder = root / "source"
			destination_folder = root / "destination"
			source_folder.mkdir()
			destination_folder.mkdir()
			(source_folder / "The Amazing Spider-Man 1963 #1.cbz").write_text("regular", encoding="utf-8")
			(source_folder / "The Amazing Spider-Man 1963 Annual '64.cbz").write_text("annual", encoding="utf-8")
			(source_folder / "The Amazing Spider-Man 1963 #999.cbz").write_text("missing", encoding="utf-8")
			_create_database(database_path)
			config_path = root / "config.json"
			log_path = root / "organizer.log"
			config_path.write_text(
				json.dumps(
					{
						"reading_order_path": str(database_path),
						"destination_folder": str(destination_folder),
						"log_path": str(log_path),
						"source_folders": [
							{
								"path": str(source_folder),
								"run": "The Amazing Spider-Man",
								"volume": 1,
								"annual_run": "Amazing Spider-Man Annual",
								"annual_volume": 1,
							}
						],
					}
				),
				encoding="utf-8",
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = main(["--config", str(config_path), "--dry-run"])

			self.assertEqual(exit_code, 0)
			report = output.getvalue()
			log = log_path.read_text(encoding="utf-8")
			self.assertIn("Unmatched scanned files:", report)
			self.assertIn(r"source\The Amazing Spider-Man 1963 #999.cbz", report)
			self.assertIn(
				r"source\The Amazing Spider-Man 1963 #1.cbz -> 00001 - The Amazing Spider-Man 1963 #1.cbz",
				report,
			)
			self.assertIn(
				r"source\The Amazing Spider-Man 1963 Annual '64.cbz -> 00002 - The Amazing Spider-Man 1963 Annual '64.cbz",
				report,
			)
			self.assertEqual(report, log)
			self.assertFalse((destination_folder / "00001 - The Amazing Spider-Man 1963 #1.cbz").exists())
		finally:
			shutil.rmtree(root, ignore_errors=True)

	def test_config_volume_prevents_cross_volume_issue_matches(self) -> None:
		with self._organizer_fixture() as fixture:
			(fixture["source"] / "The Amazing Spider-Man 1963 #1.cbz").write_text("wrong-volume", encoding="utf-8")
			_create_database(fixture["db"])
			_write_config(
				fixture["config"],
				fixture["db"],
				fixture["destination"],
				fixture["log"],
				fixture["source"],
				volume=2,
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = main(["--config", str(fixture["config"]), "--dry-run"])

			self.assertEqual(exit_code, 0)
			report = output.getvalue()
			self.assertIn(r"source\The Amazing Spider-Man 1963 #1.cbz", report)
			self.assertIn("Conversions:\n  (none)", report)

	def _organizer_fixture(self):
		return _OrganizerFixture()


def _create_database(database_path: Path) -> None:
	connection = sqlite3.connect(database_path)
	try:
		connection.executescript(
			"""
			PRAGMA foreign_keys = ON;
			CREATE TABLE comic_runs (
				id TEXT PRIMARY KEY,
				title TEXT NOT NULL,
				volume TEXT,
				years TEXT,
				category TEXT NOT NULL,
				publication_type TEXT,
				universe_hint TEXT,
				lead_characters TEXT,
				priority TEXT NOT NULL,
				marvel_url TEXT,
				marvel_issue_count INTEGER,
				notes TEXT
			);
			CREATE TABLE story_arcs (
				id TEXT PRIMARY KEY,
				title TEXT NOT NULL,
				start_date TEXT NOT NULL,
				start_date_precision TEXT NOT NULL,
				end_date TEXT,
				end_date_precision TEXT NOT NULL DEFAULT 'unknown'
			);
			CREATE TABLE issues (
				id TEXT PRIMARY KEY,
				cand_id TEXT NOT NULL,
				issue_number TEXT NOT NULL,
				release_date TEXT NOT NULL,
				release_date_precision TEXT NOT NULL,
				story_arc_id TEXT NOT NULL,
				sort_order INTEGER,
				UNIQUE (cand_id, issue_number),
				FOREIGN KEY (cand_id) REFERENCES comic_runs(id) ON DELETE CASCADE,
				FOREIGN KEY (story_arc_id) REFERENCES story_arcs(id)
			);
			"""
		)
		connection.executemany(
			"""
			INSERT INTO comic_runs (id, title, volume, years, category, priority)
			VALUES (?, ?, ?, ?, ?, ?)
			""",
			[
				("CAND-000002", "The Amazing Spider-Man", "1", "1963-1998", "core", "P0"),
				("CAND-000003", "Amazing Spider-Man Annual", "1", "1964-1994", "annual", "P0"),
				("CAND-000024", "The Amazing Spider-Man", "2", "1999-2013", "core", "P0"),
			],
		)
		connection.executemany(
			"""
			INSERT INTO story_arcs (id, title, start_date, start_date_precision)
			VALUES (?, ?, ?, ?)
			""",
			[
				("LOCAL-ARC-ASM-1", "The Amazing Spider-Man #1", "1962-12-10", "day"),
				("LOCAL-ARC-ASM-ANNUAL-1", "Amazing Spider-Man Annual #1", "1964-06-11", "day"),
			],
		)
		connection.executemany(
			"""
			INSERT INTO issues (
				id, cand_id, issue_number, release_date, release_date_precision, story_arc_id, sort_order
			)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			""",
			[
				("FANDOM-ISS-CAND-000002-1", "CAND-000002", "1", "1962-12-10", "day", "LOCAL-ARC-ASM-1", None),
				("FANDOM-ISS-CAND-000003-1", "CAND-000003", "1", "1964-06-11", "day", "LOCAL-ARC-ASM-ANNUAL-1", None),
			],
		)
		connection.commit()
	finally:
		connection.close()


class _OrganizerFixture:
	def __enter__(self):
		self.root = Path.cwd() / ".test-tmp" / "organizer-volume"
		shutil.rmtree(self.root, ignore_errors=True)
		self.root.mkdir(parents=True)
		self.source = self.root / "source"
		self.destination = self.root / "destination"
		self.source.mkdir()
		self.destination.mkdir()
		return {
			"root": self.root,
			"db": self.root / "database.db",
			"config": self.root / "config.json",
			"log": self.root / "organizer.log",
			"source": self.source,
			"destination": self.destination,
		}

	def __exit__(self, exc_type, exc_value, traceback):
		shutil.rmtree(self.root, ignore_errors=True)
		return False


def _write_config(
	config_path: Path,
	database_path: Path,
	destination_folder: Path,
	log_path: Path,
	source_folder: Path,
	*,
	volume: int,
) -> None:
	config_path.write_text(
		json.dumps(
			{
				"reading_order_path": str(database_path),
				"destination_folder": str(destination_folder),
				"log_path": str(log_path),
				"source_folders": [
					{
						"path": str(source_folder),
						"run": "The Amazing Spider-Man",
						"volume": volume,
						"annual_run": "Amazing Spider-Man Annual",
						"annual_volume": 1,
					}
				],
			}
		),
		encoding="utf-8",
	)


if __name__ == "__main__":
	unittest.main()
