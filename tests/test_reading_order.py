import json
import unittest
from pathlib import Path

from helpers import temporary_directory
from reading_order import ReadingOrderError, read_entries_from_json, read_reading_order


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

	def test_requires_run_volume_and_issue(self):
		with self.assertRaises(ReadingOrderError):
			read_entries_from_json({"entries": [{"run": "Run", "issue": "#1"}]})


if __name__ == "__main__":
	unittest.main()
