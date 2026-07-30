import unittest
from pathlib import Path

from matcher import match_candidates
from models import ParsedCandidate, ReadingOrderEntry


class MatcherTests(unittest.TestCase):
	def test_matches_reading_entry_to_candidate(self):
		result = match_candidates(
			(ReadingOrderEntry(position=1, run="Run", issue_label="1"),),
			(ParsedCandidate(run="Run", issue_number="001", is_annual=False, source_path=Path("one.cbz"), raw_name="one.cbz", source_order=0),),
		)

		self.assertEqual(1, len(result.matches))
		self.assertEqual("0001 - Run #1.cbz", result.matches[0].canonical_name)
		self.assertEqual((), result.unmatched_entries)

	def test_reports_unmatched_entry_silently_for_processor(self):
		result = match_candidates((ReadingOrderEntry(position=1, run="Run", issue_label="1"),), ())

		self.assertEqual((), result.matches)
		self.assertEqual(1, len(result.unmatched_entries))

	def test_reports_unmatched_candidate(self):
		result = match_candidates(
			(ReadingOrderEntry(position=1, run="Run", issue_label="1"),),
			(ParsedCandidate(run="Other", issue_number="1", is_annual=False, source_path=Path("other.cbz"), raw_name="other.cbz", source_order=0),),
		)

		self.assertEqual(1, len(result.unmatched_candidates))

	def test_first_candidate_wins_and_duplicate_is_reported(self):
		winner = ParsedCandidate(run="Run", issue_number="1", is_annual=False, source_path=Path("a.cbz"), raw_name="a.cbz", source_order=0)
		duplicate = ParsedCandidate(run="Run", issue_number="1", is_annual=False, source_path=Path("b.cbz"), raw_name="b.cbz", source_order=1)

		result = match_candidates((ReadingOrderEntry(position=1, run="Run", issue_label="1"),), (duplicate, winner))

		self.assertEqual(Path("a.cbz"), result.matches[0].source_path)
		self.assertEqual(1, len(result.duplicate_candidates))
		self.assertEqual(Path("b.cbz"), result.duplicate_candidates[0].duplicate.source_path)
		self.assertEqual((), result.unmatched_candidates)

	def test_uses_candidate_output_name_for_destination_filename(self):
		result = match_candidates(
			(ReadingOrderEntry(position=455, run="The Amazing Spider-Man", issue_label="396"),),
			(
				ParsedCandidate(
					run="The Amazing Spider-Man",
					issue_number="396",
					is_annual=False,
					source_path=Path("issue.cbz"),
					raw_name="issue.cbz",
					source_order=0,
					output_name="Amazing Spider-Man",
				),
			),
		)

		self.assertEqual("Amazing Spider-Man", result.matches[0].run)
		self.assertEqual("0455 - Amazing Spider-Man #396.cbz", result.matches[0].canonical_name)

	def test_uses_annual_output_name_for_destination_filename(self):
		result = match_candidates(
			(ReadingOrderEntry(position=73, run="Amazing Spider-Man Annual", issue_label="2"),),
			(
				ParsedCandidate(
					run="Amazing Spider-Man Annual",
					issue_number="2",
					is_annual=True,
					source_path=Path("annual.cbz"),
					raw_name="annual.cbz",
					source_order=0,
					output_name="The Amazing Spider-Man Annual",
				),
			),
		)

		self.assertEqual("0073 - The Amazing Spider-Man Annual #2.cbz", result.matches[0].canonical_name)
		self.assertTrue(result.matches[0].is_annual)

	def test_volume_is_part_of_match_key(self):
		result = match_candidates(
			(
				ReadingOrderEntry(position=1, run="The Amazing Spider-Man", issue_label="1", volume="1"),
				ReadingOrderEntry(position=1404, run="The Amazing Spider-Man", issue_label="1", volume="2"),
			),
			(
				ParsedCandidate(
					run="The Amazing Spider-Man",
					volume="2",
					issue_number="1",
					is_annual=False,
					source_path=Path("v2 001.cbz"),
					raw_name="v2 001.cbz",
					source_order=0,
					output_name="The Amazing Spider-Man",
				),
			),
		)

		self.assertEqual(1, len(result.matches))
		self.assertEqual(1404, result.matches[0].position)
		self.assertEqual(Path("v2 001.cbz"), result.matches[0].source_path)
		self.assertEqual(1, len(result.unmatched_entries))


if __name__ == "__main__":
	unittest.main()
