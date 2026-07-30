import unittest
from pathlib import Path

from models import ParsedCandidate, ReadingOrderEntry
from organizer import filter_completed_candidates, split_existing_entries


class OrganizerTests(unittest.TestCase):
	def test_split_existing_entries_uses_destination_positions(self):
		entries = (
			ReadingOrderEntry(position=1, run="Run", issue_label="1"),
			ReadingOrderEntry(position=455, run="Amazing Spider-Man", issue_label="396"),
			ReadingOrderEntry(position=456, run="Amazing Spider-Man", issue_label="397"),
		)

		pending_entries, completed_entries = split_existing_entries(entries, frozenset({455}))

		self.assertEqual((entries[0], entries[2]), pending_entries)
		self.assertEqual((entries[1],), completed_entries)

	def test_filter_completed_candidates_ignores_already_added_issues(self):
		completed_entries = (ReadingOrderEntry(position=455, run="Amazing Spider-Man", issue_label="396"),)
		candidate_for_completed_entry = ParsedCandidate(
			run="Amazing Spider-Man",
			issue_number="0396",
			is_annual=False,
			source_path=Path("already-added.cbz"),
			raw_name="already-added.cbz",
			source_order=0,
		)
		candidate_for_pending_entry = ParsedCandidate(
			run="Amazing Spider-Man",
			issue_number="397",
			is_annual=False,
			source_path=Path("pending.cbz"),
			raw_name="pending.cbz",
			source_order=0,
		)

		filtered_candidates = filter_completed_candidates(
			(candidate_for_completed_entry, candidate_for_pending_entry),
			completed_entries,
		)

		self.assertEqual((candidate_for_pending_entry,), filtered_candidates)


if __name__ == "__main__":
	unittest.main()
