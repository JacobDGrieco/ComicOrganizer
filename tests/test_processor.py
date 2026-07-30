import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import temporary_directory
from models import MatchedComic
from processor import find_existing_positions, process_matches


class ProcessorTests(unittest.TestCase):
	def test_finds_existing_destination_positions(self):
		with temporary_directory() as temp_dir:
			destination_path = Path(temp_dir)
			(destination_path / "0001 - Run #1.cbz").write_bytes(b"comic")
			(destination_path / "0455 - Amazing Spider-Man #396.cbz").write_bytes(b"comic")
			(destination_path / "notes.txt").write_text("skip", encoding="utf-8")

			self.assertEqual(frozenset({1, 455}), find_existing_positions(destination_path))

	def test_dry_run_does_not_move_file(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			source_path = base_path / "Issue #1.cbz"
			destination_path = base_path / "destination"
			source_path.write_bytes(b"comic")
			destination_path.mkdir()

			with contextlib.redirect_stdout(io.StringIO()):
				summary = process_matches((_match(source_path),), destination_path, dry_run=True)

			self.assertTrue(source_path.exists())
			self.assertFalse((destination_path / "0001 - Run #1.cbz").exists())
			self.assertEqual(0, summary.moved)

	def test_moves_file(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			source_path = base_path / "Issue #1.cbz"
			destination_path = base_path / "destination"
			source_path.write_bytes(b"comic")
			destination_path.mkdir()

			with contextlib.redirect_stdout(io.StringIO()):
				summary = process_matches((_match(source_path),), destination_path)

			self.assertFalse(source_path.exists())
			self.assertTrue((destination_path / "0001 - Run #1.cbz").exists())
			self.assertEqual(1, summary.moved)

	def test_skips_when_position_prefix_already_exists(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			source_path = base_path / "Issue #1.cbz"
			destination_path = base_path / "destination"
			source_path.write_bytes(b"comic")
			destination_path.mkdir()
			(destination_path / "0001 - Existing #1.cbz").write_bytes(b"existing")

			with contextlib.redirect_stdout(io.StringIO()):
				summary = process_matches((_match(source_path),), destination_path)

			self.assertTrue(source_path.exists())
			self.assertEqual(1, summary.skipped)

	def test_move_failure_does_not_raise(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			source_path = base_path / "Issue #1.cbz"
			destination_path = base_path / "destination"
			source_path.write_bytes(b"comic")
			destination_path.mkdir()

			with patch("processor.shutil.move", side_effect=OSError("locked")):
				with contextlib.redirect_stdout(io.StringIO()):
					summary = process_matches((_match(source_path),), destination_path)

			self.assertEqual(1, summary.failed)
			self.assertEqual("locked", summary.results[0].error)


def _match(source_path: Path) -> MatchedComic:
	return MatchedComic(
		position=1,
		run="Run",
		issue_label="1",
		canonical_name="0001 - Run #1.cbz",
		source_path=source_path,
	)


if __name__ == "__main__":
	unittest.main()
