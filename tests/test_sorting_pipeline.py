from __future__ import annotations

import contextlib
import io
import json
import shutil
import sqlite3
import unittest
from pathlib import Path

from sorting.list_order import build_list_report, format_report as format_list_report
from sorting.list_order import main as list_main
from sorting.missing_entries import build_missing_entries_report, format_report
from sorting.missing_entries import main as missing_main
from sorting.models import ReadingOrderEntry
from sorting.organizer import main
from sorting.reindex_output import main as reindex_main


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

	def test_list_order_report_includes_runs_and_all_issues(self) -> None:
		reading_order = (
			ReadingOrderEntry(
				position=1,
				run="Amazing Fantasy",
				volume="1",
				issue_label="15",
				run_years="1962",
				release_date="1962-06-05",
			),
			ReadingOrderEntry(
				position=2,
				run="The Amazing Spider-Man",
				volume="1",
				issue_label="1",
				run_years="1963-1998",
				release_date="1962-12-10",
			),
			ReadingOrderEntry(
				position=3,
				run="The Amazing Spider-Man",
				volume="1",
				issue_label="2",
				run_years="1963-1998",
				release_date="1963-03-12",
			),
		)

		lines = format_list_report(build_list_report(reading_order))

		self.assertEqual(
			lines,
			[
				"Comic runs:",
				"  00001 - Amazing Fantasy v1 (1962)",
				"  00002 - The Amazing Spider-Man v1 (1963-1998)",
				"",
				"Sort order:",
				"  00001 - Amazing Fantasy v1 #15 (1962-06-05)",
				"  00002 - The Amazing Spider-Man v1 #1 (1962-12-10)",
				"  00003 - The Amazing Spider-Man v1 #2 (1963-03-12)",
			],
		)

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
			(source_folder / "The Amazing Spider-Man (1963) #1.cbz").write_text("regular", encoding="utf-8")
			(source_folder / "The Amazing Spider-Man (1963) #100.cbz").write_text("regular", encoding="utf-8")
			(source_folder / "The Amazing Spider-Man (1963) Annual '64.cbz").write_text("annual", encoding="utf-8")
			(source_folder / "The Amazing Spider-Man (1963) #-1.cbz").write_text("missing", encoding="utf-8")
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
			self.assertIn(r"source\The Amazing Spider-Man (1963) #-1.cbz", report)
			self.assertIn(
				r"source\The Amazing Spider-Man (1963) #1.cbz -> 00001 - The Amazing Spider-Man (1963) #1.cbz",
				report,
			)
			self.assertIn(
				r"source\The Amazing Spider-Man (1963) Annual '64.cbz -> 00002 - The Amazing Spider-Man (1963) Annual '64.cbz",
				report,
			)
			self.assertIn(
				r"source\The Amazing Spider-Man (1963) #100.cbz -> 00003 - The Amazing Spider-Man (1963) #100.cbz",
				report,
			)
			self.assertEqual(report, log)
			self.assertFalse((destination_folder / "00001 - The Amazing Spider-Man (1963) #1.cbz").exists())
		finally:
			shutil.rmtree(root, ignore_errors=True)

	def test_organizer_defaults_to_config_logs_folder(self) -> None:
		with self._organizer_fixture() as fixture:
			(fixture["source"] / "The Amazing Spider-Man 1963 #1.cbz").write_text("regular", encoding="utf-8")
			_create_database(fixture["db"])
			config_path = fixture["config"]
			config_path.write_text(
				json.dumps(
					{
						"reading_order_path": str(fixture["db"]),
						"destination_folder": str(fixture["destination"]),
						"source_folders": [
							{
								"path": str(fixture["source"]),
								"run": "The Amazing Spider-Man",
								"volume": 1,
							}
						],
					}
				),
				encoding="utf-8",
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = main(["--config", str(config_path), "--dry-run"])

			log_path = fixture["root"] / "logs" / "comic-organizer.log"
			self.assertEqual(exit_code, 0)
			self.assertTrue(log_path.is_file())
			self.assertEqual(output.getvalue(), log_path.read_text(encoding="utf-8"))

	def test_missing_entries_defaults_to_config_logs_folder(self) -> None:
		with self._organizer_fixture() as fixture:
			_create_database(fixture["db"])
			(fixture["destination"] / "00001 - The Amazing Spider-Man 1963 #1.cbz").write_text("one", encoding="utf-8")
			(fixture["destination"] / "00003 - The Amazing Spider-Man 1963 #100.cbz").write_text("three", encoding="utf-8")
			config_path = fixture["config"]
			config_path.write_text(
				json.dumps(
					{
						"reading_order_path": str(fixture["db"]),
						"destination_folder": str(fixture["destination"]),
						"source_folders": [
							{
								"path": str(fixture["source"]),
								"run": "The Amazing Spider-Man",
								"volume": 1,
							}
						],
					}
				),
				encoding="utf-8",
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = missing_main(["--config", str(config_path)])

			log_path = fixture["root"] / "logs" / "missing-entries.log"
			self.assertEqual(exit_code, 0)
			self.assertTrue(log_path.is_file())
			self.assertEqual(output.getvalue(), log_path.read_text(encoding="utf-8"))
			self.assertIn("Missing entries in range: 1", output.getvalue())

	def test_list_order_defaults_to_config_logs_folder(self) -> None:
		with self._organizer_fixture() as fixture:
			_create_database(fixture["db"])
			config_path = fixture["config"]
			config_path.write_text(
				json.dumps(
					{
						"reading_order_path": str(fixture["db"]),
						"destination_folder": str(fixture["destination"]),
						"source_folders": [
							{
								"path": str(fixture["source"]),
								"run": "The Amazing Spider-Man",
								"volume": 1,
							}
						],
					}
				),
				encoding="utf-8",
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = list_main(["--config", str(config_path)])

			log_path = fixture["root"] / "logs" / "reading-order-list.log"
			self.assertEqual(exit_code, 0)
			self.assertTrue(log_path.is_file())
			self.assertEqual(output.getvalue(), log_path.read_text(encoding="utf-8"))
			self.assertIn("Comic runs:", output.getvalue())
			self.assertIn("Sort order:", output.getvalue())

	def test_reindex_output_dry_run_uses_current_database_order(self) -> None:
		with self._organizer_fixture() as fixture:
			_create_database(fixture["db"])
			(fixture["destination"] / "00003 - The Amazing Spider-Man (1963) #1.cbz").write_text("one", encoding="utf-8")
			(fixture["destination"] / "00001 - The Amazing Spider-Man (1963) #100.cbz").write_text("three", encoding="utf-8")
			_write_config(
				fixture["config"],
				fixture["db"],
				fixture["destination"],
				fixture["log"],
				fixture["source"],
				volume=1,
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = reindex_main(["--config", str(fixture["config"])])

			report = output.getvalue()
			self.assertEqual(exit_code, 0)
			self.assertIn(
				"would rename: 00003 - The Amazing Spider-Man (1963) #1.cbz -> 00001 - The Amazing Spider-Man (1963) #1.cbz",
				report,
			)
			self.assertIn(
				"would rename: 00001 - The Amazing Spider-Man (1963) #100.cbz -> 00003 - The Amazing Spider-Man (1963) #100.cbz",
				report,
			)
			self.assertTrue((fixture["destination"] / "00003 - The Amazing Spider-Man (1963) #1.cbz").exists())

	def test_reindex_output_apply_swaps_prefixes_safely(self) -> None:
		with self._organizer_fixture() as fixture:
			_create_database(fixture["db"])
			(fixture["destination"] / "00003 - The Amazing Spider-Man (1963) #1.cbz").write_text("one", encoding="utf-8")
			(fixture["destination"] / "00001 - The Amazing Spider-Man (1963) #100.cbz").write_text("three", encoding="utf-8")
			_write_config(
				fixture["config"],
				fixture["db"],
				fixture["destination"],
				fixture["log"],
				fixture["source"],
				volume=1,
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = reindex_main(["--config", str(fixture["config"]), "--apply"])

			self.assertEqual(exit_code, 0)
			self.assertTrue((fixture["destination"] / "00001 - The Amazing Spider-Man (1963) #1.cbz").exists())
			self.assertTrue((fixture["destination"] / "00003 - The Amazing Spider-Man (1963) #100.cbz").exists())
			self.assertFalse((fixture["destination"] / "00003 - The Amazing Spider-Man (1963) #1.cbz").exists())

	def test_reindex_output_prefers_already_correct_duplicate(self) -> None:
		with self._organizer_fixture() as fixture:
			_create_database(fixture["db"])
			(fixture["destination"] / "00001 - The Amazing Spider-Man (1963) #1.cbz").write_text("correct", encoding="utf-8")
			(fixture["destination"] / "00002 - The Amazing Spider-Man (1963) #1.cbz").write_text("duplicate", encoding="utf-8")
			_write_config(
				fixture["config"],
				fixture["db"],
				fixture["destination"],
				fixture["log"],
				fixture["source"],
				volume=1,
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = reindex_main(["--config", str(fixture["config"])])

			report = output.getvalue()
			self.assertEqual(exit_code, 0)
			self.assertIn("duplicate match for The Amazing Spider-Man v1 #1", report)
			self.assertIn("winner is 00001 - The Amazing Spider-Man (1963) #1.cbz", report)
			self.assertIn("No index changes needed.", report)

	def test_reindex_output_matches_postfixed_year_without_source_folder(self) -> None:
		with self._organizer_fixture() as fixture:
			_create_database(fixture["db"])
			_add_amazing_fantasy_issue(fixture["db"])
			(fixture["destination"] / "00099 - Amazing Fantasy #15 (1962).cbz").write_text("fantasy", encoding="utf-8")
			_write_config(
				fixture["config"],
				fixture["db"],
				fixture["destination"],
				fixture["log"],
				fixture["source"],
				volume=1,
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = reindex_main(["--config", str(fixture["config"])])

			report = output.getvalue()
			self.assertEqual(exit_code, 0)
			self.assertIn(
				"would rename: 00099 - Amazing Fantasy #15 (1962).cbz -> 00001 - Amazing Fantasy #15 (1962).cbz",
				report,
			)

	def test_reindex_output_uses_year_mismatch_when_no_exact_source_year_exists(self) -> None:
		with self._organizer_fixture() as fixture:
			_create_database(fixture["db"])
			(fixture["destination"] / "00099 - The Amazing Spider-Man (1963) #1.cbz").write_text("one", encoding="utf-8")
			_write_config(
				fixture["config"],
				fixture["db"],
				fixture["destination"],
				fixture["log"],
				fixture["root"] / "The Amazing Spider-Man (1964)",
				volume=1,
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = reindex_main(["--config", str(fixture["config"])])

			report = output.getvalue()
			self.assertEqual(exit_code, 0)
			self.assertIn(
				"would rename: 00099 - The Amazing Spider-Man (1963) #1.cbz -> 00001 - The Amazing Spider-Man (1963) #1.cbz",
				report,
			)

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

	def test_source_issue_aliases_match_database_issue_numbers(self) -> None:
		with self._organizer_fixture() as fixture:
			(fixture["source"] / "The Amazing Spider-Man (2018) #16.HU.cbz").write_text("side", encoding="utf-8")
			_create_database(fixture["db"])
			_write_config(
				fixture["config"],
				fixture["db"],
				fixture["destination"],
				fixture["log"],
				fixture["source"],
				volume=5,
				issue_aliases={"16.HU": "16.1"},
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = main(["--config", str(fixture["config"]), "--dry-run"])

			self.assertEqual(exit_code, 0)
			report = output.getvalue()
			self.assertIn(
				r"source\The Amazing Spider-Man (2018) #16.HU.cbz -> 00004 - The Amazing Spider-Man (2018) #16.HU.cbz",
				report,
			)
			self.assertNotIn("Unmatched scanned files:\n  source\\The Amazing Spider-Man (2018) #16.HU.cbz", report)

	def test_unicode_half_issue_alias_matches_database_issue_number(self) -> None:
		with self._organizer_fixture() as fixture:
			(fixture["source"] / "Spider-Man Unlimited (1999) #½.cbz").write_text("half", encoding="utf-8")
			_create_database(fixture["db"])
			_add_spider_man_unlimited_half_issue(fixture["db"])
			_write_config(
				fixture["config"],
				fixture["db"],
				fixture["destination"],
				fixture["log"],
				fixture["source"],
				run="Spider-Man Unlimited",
				volume=2,
				issue_aliases={"½": "1/2"},
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = main(["--config", str(fixture["config"]), "--dry-run"])

			self.assertEqual(exit_code, 0)
			report = output.getvalue()
			self.assertIn(
				r"source\Spider-Man Unlimited (1999) #½.cbz -> 00004 - Spider-Man Unlimited (1999) #½.cbz",
				report,
			)

	def test_special_issue_uses_configured_special_run(self) -> None:
		with self._organizer_fixture() as fixture:
			(fixture["source"] / "Superior Spider-Man Team-Up (2013) Special #1.cbz").write_text("special", encoding="utf-8")
			_create_database(fixture["db"])
			_add_superior_spider_man_team_up_special(fixture["db"])
			_write_config(
				fixture["config"],
				fixture["db"],
				fixture["destination"],
				fixture["log"],
				fixture["source"],
				run="Superior Spider-Man Team-Up",
				volume=1,
				special_run="Superior Spider-Man Team-Up Special",
				special_volume=1,
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = main(["--config", str(fixture["config"]), "--dry-run"])

			self.assertEqual(exit_code, 0)
			report = output.getvalue()
			self.assertIn(
				r"source\Superior Spider-Man Team-Up (2013) Special #1.cbz -> 00004 - Superior Spider-Man Team-Up (2013) Special #1.cbz",
				report,
			)

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
				("CAND-000007", "The Amazing Spider-Man", "5", "2018-2022", "core", "P0"),
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
				("LOCAL-ARC-ASM-100", "The Amazing Spider-Man #100", "1971-09-01", "day"),
				("LOCAL-ARC-ASM-2018-16-1", "The Amazing Spider-Man (2018) #16.1", "2019-03-06", "day"),
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
				("FANDOM-ISS-CAND-000002-100", "CAND-000002", "100", "1971-09-01", "day", "LOCAL-ARC-ASM-100", None),
				("FANDOM-ISS-CAND-000007-16-POINT-1", "CAND-000007", "16.1", "2019-03-06", "day", "LOCAL-ARC-ASM-2018-16-1", None),
			],
		)
		connection.commit()
	finally:
		connection.close()


def _add_spider_man_unlimited_half_issue(database_path: Path) -> None:
	connection = sqlite3.connect(database_path)
	try:
		connection.execute(
			"""
			INSERT INTO comic_runs (id, title, volume, years, category, priority)
			VALUES (?, ?, ?, ?, ?, ?)
			""",
			("CAND-000309", "Spider-Man Unlimited", "2", "1999-2000", "core", "P0"),
		)
		connection.execute(
			"""
			INSERT INTO story_arcs (id, title, start_date, start_date_precision)
			VALUES (?, ?, ?, ?)
			""",
			("LOCAL-ARC-SMU-2-HALF", "Spider-Man Unlimited #1/2", "1999", "year"),
		)
		connection.execute(
			"""
			INSERT INTO issues (
				id, cand_id, issue_number, release_date, release_date_precision, story_arc_id, sort_order
			)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			""",
			("FANDOM-ISS-CAND-000309-1-SLASH-2", "CAND-000309", "1/2", "1999", "year", "LOCAL-ARC-SMU-2-HALF", None),
		)
		connection.commit()
	finally:
		connection.close()


def _add_amazing_fantasy_issue(database_path: Path) -> None:
	connection = sqlite3.connect(database_path)
	try:
		connection.execute(
			"""
			INSERT INTO comic_runs (id, title, volume, years, category, priority)
			VALUES (?, ?, ?, ?, ?, ?)
			""",
			("CAND-000001", "Amazing Fantasy", "1", "1962", "core", "P0"),
		)
		connection.execute(
			"""
			INSERT INTO story_arcs (id, title, start_date, start_date_precision)
			VALUES (?, ?, ?, ?)
			""",
			("LOCAL-ARC-AF-15", "Amazing Fantasy #15", "1962-06-05", "day"),
		)
		connection.execute(
			"""
			INSERT INTO issues (
				id, cand_id, issue_number, release_date, release_date_precision, story_arc_id, sort_order
			)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			""",
			("FANDOM-ISS-CAND-000001-15", "CAND-000001", "15", "1962-06-05", "day", "LOCAL-ARC-AF-15", None),
		)
		connection.commit()
	finally:
		connection.close()


def _add_superior_spider_man_team_up_special(database_path: Path) -> None:
	connection = sqlite3.connect(database_path)
	try:
		connection.execute(
			"""
			INSERT INTO comic_runs (id, title, volume, years, category, priority)
			VALUES (?, ?, ?, ?, ?, ?)
			""",
			("CAND-000311", "Superior Spider-Man Team-Up Special", "1", "2013", "core", "P1"),
		)
		connection.execute(
			"""
			INSERT INTO story_arcs (id, title, start_date, start_date_precision)
			VALUES (?, ?, ?, ?)
			""",
			("LOCAL-ARC-SUPERIOR-TEAM-UP-SPECIAL-1", "Superior Spider-Man Team-Up Special #1", "2013-10-30", "day"),
		)
		connection.execute(
			"""
			INSERT INTO issues (
				id, cand_id, issue_number, release_date, release_date_precision, story_arc_id, sort_order
			)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			""",
			(
				"FANDOM-ISS-CAND-000311-1",
				"CAND-000311",
				"1",
				"2013-10-30",
				"day",
				"LOCAL-ARC-SUPERIOR-TEAM-UP-SPECIAL-1",
				None,
			),
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
	run: str = "The Amazing Spider-Man",
	volume: int,
	annual_run: str = "Amazing Spider-Man Annual",
	annual_volume: int = 1,
	special_run: str = "The Amazing Spider-Man Special",
	special_volume: int = 1,
	issue_aliases: dict[str, str] | None = None,
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
							"run": run,
							"volume": volume,
							"annual_run": annual_run,
							"annual_volume": annual_volume,
							"special_run": special_run,
							"special_volume": special_volume,
							"issue_aliases": issue_aliases or {},
						}
				],
			}
		),
		encoding="utf-8",
	)


if __name__ == "__main__":
	unittest.main()
