import unittest

from reading_order import ReadingOrderError, read_entries_from_sheet


class FakeSheet:
	def __init__(self, rows):
		self._rows = rows

	def iter_rows(self, values_only):
		return iter(self._rows)


class ReadingOrderTests(unittest.TestCase):
	def test_reads_entries_in_row_order(self):
		sheet = FakeSheet(
			[
				("Run", "Volume", "Issue", "Ordering note"),
				("Amazing Fantasy", 1, "#1", ""),
				("The Amazing Spider-Man", 1, "#001", ""),
			]
		)

		entries = read_entries_from_sheet(sheet, {"Amazing Fantasy": {"1": "15"}})

		self.assertEqual(1, entries[0].position)
		self.assertEqual("Amazing Fantasy", entries[0].run)
		self.assertEqual("1", entries[0].volume)
		self.assertEqual("15", entries[0].issue_label)
		self.assertEqual(2, entries[1].position)
		self.assertEqual("1", entries[1].issue_label)

	def test_position_uses_sheet_row_number_minus_header(self):
		sheet = FakeSheet(
			[
				("Run", "Volume", "Issue"),
				("Run", 1, "#1"),
				(None, None, None),
				("Run", 1, "#396"),
			]
		)

		entries = read_entries_from_sheet(sheet)

		self.assertEqual(1, entries[0].position)
		self.assertEqual(3, entries[1].position)
		self.assertEqual("396", entries[1].issue_label)

	def test_requires_run_and_issue_headers(self):
		sheet = FakeSheet([("Name", "Issue")])

		with self.assertRaises(ReadingOrderError):
			read_entries_from_sheet(sheet)


if __name__ == "__main__":
	unittest.main()
