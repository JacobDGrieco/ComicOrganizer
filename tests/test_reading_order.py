import json
import sqlite3
import unittest
from pathlib import Path

from helpers import temporary_directory
from reading_order import ReadingOrderError, read_entries_from_json, read_entries_from_sqlite, read_reading_order


class ReadingOrderTests(unittest.TestCase):
	def test_reads_entries_in_json_order(self):
		entries = read_entries_from_json(
			{
				"entries": [
					{"run": "Amazing Fantasy", "volume": 1, "issue": "#1", "ordering_note": ""},
					{"run": "The Amazing Spider-Man", "volume": 1, "issue": "#001", "ordering_note": ""},
				]
			},
			{"Amazing Fantasy": {"1": "15"}},
		)

		self.assertEqual(1, entries[0].position)
		self.assertEqual("Amazing Fantasy", entries[0].run)
		self.assertEqual("1", entries[0].volume)
		self.assertEqual("15", entries[0].issue_label)
		self.assertEqual(2, entries[1].position)
		self.assertEqual("1", entries[1].issue_label)

	def test_reads_bare_json_array(self):
		entries = read_entries_from_json(
			[
				{"Run": "Run", "Volume": 1, "Issue": "#1"},
				{"Run": "Run", "Volume": 1, "Issue": "#396"},
			]
		)

		self.assertEqual(1, entries[0].position)
		self.assertEqual(2, entries[1].position)
		self.assertEqual("396", entries[1].issue_label)

	def test_reads_json_file(self):
		with temporary_directory() as temp_dir:
			reading_order_path = Path(temp_dir) / "reading_order.json"
			reading_order_path.write_text(
				json.dumps({"entries": [{"run": "Run", "volume": "1", "issue": "#1"}]}),
				encoding="utf-8",
			)

			entries = read_reading_order(reading_order_path)

			self.assertEqual("Run", entries[0].run)

	def test_reads_sqlite_file_in_story_arc_order(self):
		with temporary_directory() as temp_dir:
			reading_order_path = Path(temp_dir) / "reading_order.db"
			create_sqlite_reading_order(reading_order_path)

			entries = read_reading_order(reading_order_path)

			self.assertEqual("Run", entries[0].run)
			self.assertEqual("1", entries[0].issue_label)
			self.assertEqual("2", entries[1].issue_label)

	def test_applies_issue_overrides_to_sqlite_entries(self):
		with temporary_directory() as temp_dir:
			reading_order_path = Path(temp_dir) / "reading_order.db"
			create_sqlite_reading_order(reading_order_path)

			entries = read_entries_from_sqlite(reading_order_path, {"Run": {"1": "15"}})

			self.assertEqual("15", entries[0].issue_label)

	def test_requires_run_volume_and_issue(self):
		with self.assertRaises(ReadingOrderError):
			read_entries_from_json({"entries": [{"run": "Run", "issue": "#1"}]})


def create_sqlite_reading_order(path: Path) -> None:
	connection = sqlite3.connect(path)
	try:
		connection.executescript(
			"""
			CREATE TABLE comic_runs (
				id TEXT PRIMARY KEY,
				title TEXT NOT NULL,
				volume TEXT NOT NULL,
				category TEXT NOT NULL,
				priority TEXT NOT NULL
			);
			CREATE TABLE story_arcs (
				id TEXT PRIMARY KEY,
				title TEXT NOT NULL,
				start_date TEXT NOT NULL,
				start_date_precision TEXT NOT NULL
			);
			CREATE TABLE issues (
				id TEXT PRIMARY KEY,
				cand_id TEXT NOT NULL,
				issue_number TEXT NOT NULL,
				release_date TEXT NOT NULL,
				release_date_precision TEXT NOT NULL,
				story_arc_id TEXT NOT NULL
			);
			INSERT INTO comic_runs (id, title, volume, category, priority) VALUES ('CAND-1', 'Run', '1', 'Test', 'P0');
			INSERT INTO story_arcs (id, title, start_date, start_date_precision) VALUES ('ARC-2', 'Second Arc', '1963-01-01', 'day');
			INSERT INTO story_arcs (id, title, start_date, start_date_precision) VALUES ('ARC-1', 'First Arc', '1962-01-01', 'day');
			INSERT INTO issues (id, cand_id, issue_number, release_date, release_date_precision, story_arc_id)
			VALUES ('ISS-2', 'CAND-1', '2', '1963-01-01', 'day', 'ARC-2');
			INSERT INTO issues (id, cand_id, issue_number, release_date, release_date_precision, story_arc_id)
			VALUES ('ISS-1', 'CAND-1', '1', '1962-01-01', 'day', 'ARC-1');
			"""
		)
		connection.commit()
	finally:
		connection.close()


if __name__ == "__main__":
	unittest.main()
