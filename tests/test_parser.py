import unittest
from pathlib import Path

from models import SourceFile
from parser import parse_source_file


class ParserTests(unittest.TestCase):
	def test_parses_issue_hash_pattern(self):
		candidate = parse_source_file(SourceFile(path=Path("Issue #7.cbz"), run="Run", source_order=0))

		self.assertEqual("Run", candidate.run)
		self.assertEqual("7", candidate.issue_number)
		self.assertFalse(candidate.is_annual)

	def test_parses_large_issue_hash_pattern(self):
		candidate = parse_source_file(SourceFile(path=Path("Issue #589.cbz"), run="Run", source_order=0))

		self.assertEqual("589", candidate.issue_number)

	def test_parses_issue_word_without_hash(self):
		candidate = parse_source_file(SourceFile(path=Path("Issue 12.cbz"), run="Run", source_order=0))

		self.assertEqual("12", candidate.issue_number)

	def test_parses_three_digit_volume_issue_pattern(self):
		candidate = parse_source_file(SourceFile(path=Path("v1 141.cbz"), run="Run", source_order=0))

		self.assertEqual("1", candidate.volume)
		self.assertEqual("141", candidate.issue_number)

	def test_parses_filename_volume_for_volume_issue_pattern(self):
		candidate = parse_source_file(SourceFile(path=Path("v2 001.cbz"), run="Run", source_order=0, volume="1"))

		self.assertEqual("2", candidate.volume)
		self.assertEqual("1", candidate.issue_number)

	def test_parses_volume_issue_pattern_with_leading_zeroes(self):
		candidate = parse_source_file(SourceFile(path=Path("v1 010.cbz"), run="Run", source_order=0))

		self.assertEqual("10", candidate.issue_number)

	def test_parses_leading_issue_title_pattern(self):
		candidate = parse_source_file(SourceFile(path=Path("94_-_Who_Was_Joey_Z.cbz"), run="Run", source_order=0))

		self.assertEqual("Run", candidate.run)
		self.assertEqual("94", candidate.issue_number)
		self.assertFalse(candidate.is_annual)

	def test_parses_leading_zero_issue_title_pattern(self):
		candidate = parse_source_file(SourceFile(path=Path("007_-_Some_Title.cbz"), run="Run", source_order=0))

		self.assertEqual("7", candidate.issue_number)

	def test_parses_annual_pattern_and_adjusts_run(self):
		candidate = parse_source_file(SourceFile(path=Path("v1 .Annual 003.cbz"), run="Run", source_order=0))

		self.assertEqual("Run Annual", candidate.run)
		self.assertEqual("3", candidate.issue_number)
		self.assertTrue(candidate.is_annual)

	def test_parses_annual_pattern_with_extra_spacing(self):
		candidate = parse_source_file(SourceFile(path=Path("v1 .Annual  010.cbz"), run="Run", source_order=0))

		self.assertEqual("Run Annual", candidate.run)
		self.assertEqual("10", candidate.issue_number)
		self.assertTrue(candidate.is_annual)

	def test_parses_simple_annual_pattern(self):
		candidate = parse_source_file(SourceFile(path=Path("Annual 10.cbz"), run="Run", source_order=0))

		self.assertEqual("Run Annual", candidate.run)
		self.assertEqual("10", candidate.issue_number)
		self.assertTrue(candidate.is_annual)

	def test_parses_underscore_annual_pattern(self):
		candidate = parse_source_file(SourceFile(path=Path("Annual_1.cbz"), run="Run", source_order=0))

		self.assertEqual("Run Annual", candidate.run)
		self.assertEqual("1", candidate.issue_number)
		self.assertTrue(candidate.is_annual)

	def test_parses_underscore_hash_annual_pattern(self):
		candidate = parse_source_file(SourceFile(path=Path("Annual_#12.cbz"), run="Run", source_order=0))

		self.assertEqual("Run Annual", candidate.run)
		self.assertEqual("12", candidate.issue_number)
		self.assertTrue(candidate.is_annual)

	def test_parses_annual_pattern_with_year_hint(self):
		candidate = parse_source_file(SourceFile(path=Path("Annual 42 (2018).cbz"), run="Run", source_order=0))

		self.assertEqual("Run Annual", candidate.run)
		self.assertEqual("42", candidate.issue_number)
		self.assertTrue(candidate.is_annual)

	def test_annual_pattern_adjusts_output_name(self):
		candidate = parse_source_file(
			SourceFile(path=Path("v1 .Annual 010.cbz"), run="Sheet Run", source_order=0, output_name="Output Run")
		)

		self.assertEqual("Sheet Run Annual", candidate.run)
		self.assertEqual("Output Run Annual", candidate.output_name)

	def test_annual_pattern_uses_configured_annual_mapping(self):
		candidate = parse_source_file(
			SourceFile(
				path=Path("v1 .Annual 010.cbz"),
				run="The Amazing Spider-Man",
				source_order=0,
				output_name="The Amazing Spider-Man",
				volume="1",
				annual_run="Amazing Spider-Man Annual",
				annual_output_name="The Amazing Spider-Man Annual",
				annual_volume="1",
			)
		)

		self.assertEqual("Amazing Spider-Man Annual", candidate.run)
		self.assertEqual("1", candidate.volume)
		self.assertEqual("The Amazing Spider-Man Annual", candidate.output_name)
		self.assertEqual("10", candidate.issue_number)

	def test_unrecognized_filename_returns_none(self):
		self.assertIsNone(parse_source_file(SourceFile(path=Path("cover.jpg"), run="Run", source_order=0)))


if __name__ == "__main__":
	unittest.main()
