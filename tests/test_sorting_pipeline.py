from __future__ import annotations

import contextlib
import io
import json
import shutil
import sqlite3
import unittest
from pathlib import Path

from sorting.characters import character_list_path_from_config, find_duplicate_claims, read_character_claims
from sorting.config import load_config
from sorting.list_order import build_list_report, format_report as format_list_report
from sorting.list_order import main as list_main
from sorting.missing_entries import build_missing_entries_report, format_report
from sorting.missing_entries import main as missing_main
from sorting.models import ReadingOrderEntry
from sorting.organizer import main
from sorting.reading_order import read_entries_from_sqlite
from sorting.reindex_output import main as reindex_main


class OrganizerPipelineTests(unittest.TestCase):
	def test_missing_entries_report_stops_at_last_existing_position(self) -> None:
		reading_order = tuple(
			ReadingOrderEntry(
				position=position,
				run="The Amazing Spider-Man",
				volume="1",
				issue_label=str(position),
				run_years="1963-1998",
				release_date=f"1963-01-{position:02d}",
			)
			for position in range(1, 7)
		)

		report = build_missing_entries_report(reading_order, frozenset({1, 3, 5}))
		lines = format_report(report)

		self.assertEqual(report.last_existing_position, 5)
		self.assertEqual([(run.position, run.run, run.volume) for run in report.runs], [(1, "The Amazing Spider-Man", "1")])
		self.assertEqual([entry.position for entry in report.missing_entries], [2, 4])
		self.assertIn("Missing entries in range: 2", lines)
		self.assertIn("Comic runs with missing entries:", lines)
		self.assertIn("  00001 - The Amazing Spider-Man v1 (1963-1998)", lines)
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

	def test_config_relative_paths_resolve_next_to_project_config(self) -> None:
		root = Path.cwd() / ".test-tmp" / "project-config"
		shutil.rmtree(root, ignore_errors=True)
		try:
			project_root = root / "projects" / "spider-man"
			destination_folder = project_root / "organized"
			source_folder = project_root / "downloads" / "The Amazing Spider-Man"
			project_root.mkdir(parents=True)
			destination_folder.mkdir()
			source_folder.mkdir(parents=True)
			(project_root / "database.db").write_text("", encoding="utf-8")
			(project_root / "character-list.md").write_text("| Character |\n| --- |\n| Spider-Man |\n", encoding="utf-8")
			config_path = project_root / "config.json"
			config_path.write_text(
				json.dumps(
					{
						"project_name": "Spider-Man",
						"reading_order_path": "database.db",
						"destination_folder": "organized",
						"character_list_path": "character-list.md",
						"source_folders": [
							{
								"path": "downloads\\The Amazing Spider-Man",
								"run": "The Amazing Spider-Man",
								"volume": 1,
							}
						],
					}
				),
				encoding="utf-8",
			)

			config = load_config(config_path)

			self.assertEqual(config.project_name, "Spider-Man")
			self.assertEqual(config.reading_order_path, project_root / "database.db")
			self.assertEqual(config.destination_folder, destination_folder)
			self.assertEqual(config.character_list_path, project_root / "character-list.md")
			self.assertEqual(config.source_folders[0].path, source_folder)
			self.assertEqual(config.log_path, project_root / "logs" / "comic-organizer.log")
		finally:
			shutil.rmtree(root, ignore_errors=True)

	def test_character_list_duplicate_detection_uses_aliases(self) -> None:
		root = Path.cwd() / ".test-tmp" / "character-lists"
		shutil.rmtree(root, ignore_errors=True)
		try:
			root.mkdir(parents=True)
			spider_list = root / "Spider-Man.md"
			symbiote_list = root / "Symbiotes.md"
			spider_list.write_text(
				"| Character | Origin |\n| --- | --- |\n| Venom (Eddie Brock) | ASM #300 |\n",
				encoding="utf-8",
			)
			symbiote_list.write_text(
				"| Character |\n| --- |\n| Venom |\n",
				encoding="utf-8",
			)

			claims = read_character_claims(spider_list) + read_character_claims(symbiote_list)
			duplicates = find_duplicate_claims(claims)

			self.assertEqual([duplicate.key for duplicate in duplicates], ["venom"])
			self.assertEqual([claim.name for claim in duplicates[0].claims], ["Venom (Eddie Brock)", "Venom"])
		finally:
			shutil.rmtree(root, ignore_errors=True)

	def test_character_list_path_can_be_read_before_project_database_exists(self) -> None:
		root = Path.cwd() / ".test-tmp" / "character-config"
		shutil.rmtree(root, ignore_errors=True)
		try:
			project_root = root / "projects" / "x-men"
			project_root.mkdir(parents=True)
			config_path = project_root / "config.json"
			config_path.write_text(
				json.dumps(
					{
						"project_name": "X-Men",
						"character_list_path": "character-list.md",
					}
				),
				encoding="utf-8",
			)

			self.assertEqual(character_list_path_from_config(config_path), project_root / "character-list.md")
		finally:
			shutil.rmtree(root, ignore_errors=True)

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

	def test_sqlite_order_uses_release_date_for_recent_ongoing_runs(self) -> None:
		with self._organizer_fixture() as fixture:
			_create_database(fixture["db"])
			_add_recent_ordering_fixture(fixture["db"])

			entries = read_entries_from_sqlite(fixture["db"])
			entry_keys = [(entry.run, entry.issue_label) for entry in entries]

			self.assertLess(
				entry_keys.index(("Recent Ongoing Spider-Man", "1")),
				entry_keys.index(("Recent Ongoing Spider-Man", "2")),
			)
			self.assertLess(
				entry_keys.index(("Recent Limited Spider-Man", "2")),
				entry_keys.index(("Recent Limited Spider-Man", "1")),
			)

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

	def test_reindex_output_uses_source_title_alias(self) -> None:
		with self._organizer_fixture() as fixture:
			_create_database(fixture["db"])
			(fixture["destination"] / "00099 - Old Amazing Spider-Man (1963) #1.cbz").write_text("one", encoding="utf-8")
			_write_config(
				fixture["config"],
				fixture["db"],
				fixture["destination"],
				fixture["log"],
				fixture["source"],
				volume=1,
				source_title_aliases=["Old Amazing Spider-Man"],
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = reindex_main(["--config", str(fixture["config"])])

			report = output.getvalue()
			self.assertEqual(exit_code, 0)
			self.assertIn(
				"would rename: 00099 - Old Amazing Spider-Man (1963) #1.cbz -> 00001 - Old Amazing Spider-Man (1963) #1.cbz",
				report,
			)
			self.assertNotIn("no configured source title matched original filename", report)

	def test_regular_reindex_issue_ignores_annual_start_year(self) -> None:
		with self._organizer_fixture() as fixture:
			_create_database(fixture["db"])
			_add_spider_gwen_volume_two_issue(fixture["db"])
			(fixture["destination"] / "00099 - Spider-Gwen (2015) #6.cbz").write_text("gwen", encoding="utf-8")
			_write_config(
				fixture["config"],
				fixture["db"],
				fixture["destination"],
				fixture["log"],
				fixture["root"] / "Spider-Gwen (2015)(2)",
				run="Spider-Gwen",
				volume=2,
				annual_run="Spider-Gwen Annual",
				annual_volume=1,
				annual_start_year="2016",
			)

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				exit_code = reindex_main(["--config", str(fixture["config"])])

			report = output.getvalue()
			self.assertEqual(exit_code, 0)
			self.assertIn(
				"would rename: 00099 - Spider-Gwen (2015) #6.cbz -> 00004 - Spider-Gwen (2015) #6.cbz",
				report,
			)
			self.assertNotIn("no current reading-order match", report)

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


def _add_recent_ordering_fixture(database_path: Path) -> None:
	connection = sqlite3.connect(database_path)
	try:
		connection.executemany(
			"""
			INSERT INTO comic_runs (id, title, volume, years, category, publication_type, priority)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			""",
			[
				("CAND-RECENT-ONGOING", "Recent Ongoing Spider-Man", "1", "2024", "core", "Ongoing", "P0"),
				("CAND-RECENT-LIMITED", "Recent Limited Spider-Man", "1", "2024", "event", "Limited Series", "P0"),
			],
		)
		connection.executemany(
			"""
			INSERT INTO story_arcs (id, title, start_date, start_date_precision)
			VALUES (?, ?, ?, ?)
			""",
			[
				("LOCAL-ARC-RECENT-ONGOING-1", "Recent Ongoing Spider-Man #1", "2024-05-01", "day"),
				("EVENT-RECENT-ONGOING", "Recent Ongoing Event", "2024-04-01", "day"),
				("LOCAL-ARC-RECENT-LIMITED-1", "Recent Limited Spider-Man #1", "2024-05-01", "day"),
				("EVENT-RECENT-LIMITED", "Recent Limited Event", "2024-04-01", "day"),
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
				(
					"FANDOM-ISS-CAND-RECENT-ONGOING-1",
					"CAND-RECENT-ONGOING",
					"1",
					"2024-05-01",
					"day",
					"LOCAL-ARC-RECENT-ONGOING-1",
					None,
				),
				(
					"FANDOM-ISS-CAND-RECENT-ONGOING-2",
					"CAND-RECENT-ONGOING",
					"2",
					"2024-06-01",
					"day",
					"EVENT-RECENT-ONGOING",
					None,
				),
				(
					"FANDOM-ISS-CAND-RECENT-LIMITED-1",
					"CAND-RECENT-LIMITED",
					"1",
					"2024-05-01",
					"day",
					"LOCAL-ARC-RECENT-LIMITED-1",
					None,
				),
				(
					"FANDOM-ISS-CAND-RECENT-LIMITED-2",
					"CAND-RECENT-LIMITED",
					"2",
					"2024-06-01",
					"day",
					"EVENT-RECENT-LIMITED",
					None,
				),
			],
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


def _add_spider_gwen_volume_two_issue(database_path: Path) -> None:
	connection = sqlite3.connect(database_path)
	try:
		connection.execute(
			"""
			INSERT INTO comic_runs (id, title, volume, years, category, priority)
			VALUES (?, ?, ?, ?, ?, ?)
			""",
			("CAND-000052", "Spider-Gwen", "2", "2015-2018", "core", "P1"),
		)
		connection.execute(
			"""
			INSERT INTO story_arcs (id, title, start_date, start_date_precision)
			VALUES (?, ?, ?, ?)
			""",
			("LOCAL-ARC-SPIDER-GWEN-6", "Spider-Gwen #6", "2016-03-09", "day"),
		)
		connection.execute(
			"""
			INSERT INTO issues (
				id, cand_id, issue_number, release_date, release_date_precision, story_arc_id, sort_order
			)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			""",
			(
				"FANDOM-ISS-CAND-000052-6",
				"CAND-000052",
				"6",
				"2016-03-09",
				"day",
				"LOCAL-ARC-SPIDER-GWEN-6",
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
	annual_start_year: str = "",
	special_run: str = "The Amazing Spider-Man Special",
	special_volume: int = 1,
	issue_aliases: dict[str, str] | None = None,
	source_title_aliases: list[str] | None = None,
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
							"annual_start_year": annual_start_year,
							"special_run": special_run,
							"special_volume": special_volume,
							"issue_aliases": issue_aliases or {},
							"source_title_aliases": source_title_aliases or [],
						}
				],
			}
		),
		encoding="utf-8",
	)


if __name__ == "__main__":
	unittest.main()
