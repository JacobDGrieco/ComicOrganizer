import unittest
import contextlib
import io
from pathlib import Path

from helpers import temporary_directory
from models import SourceFolderConfig
from scanner import scan_source_folders


class ScannerTests(unittest.TestCase):
	def test_scans_cbz_files_only(self):
		with temporary_directory() as temp_dir:
			source_path = Path(temp_dir)
			(source_path / "Issue #2.cbz").write_bytes(b"2")
			(source_path / "Issue #1.cbz").write_bytes(b"1")
			(source_path / "notes.txt").write_text("skip", encoding="utf-8")

			files = scan_source_folders(
				(
					SourceFolderConfig(
						path=source_path,
						run="Run",
						output_name="Output Run",
						volume="2",
						annual_run="Annual Run",
						annual_output_name="Annual Output Run",
						annual_volume="1",
					),
				)
			)

			self.assertEqual(["Issue #1.cbz", "Issue #2.cbz"], [source_file.path.name for source_file in files])
			self.assertEqual(["Run", "Run"], [source_file.run for source_file in files])
			self.assertEqual(["Output Run", "Output Run"], [source_file.output_name for source_file in files])
			self.assertEqual(["2", "2"], [source_file.volume for source_file in files])
			self.assertEqual(["Annual Run", "Annual Run"], [source_file.annual_run for source_file in files])
			self.assertEqual(["Annual Output Run", "Annual Output Run"], [source_file.annual_output_name for source_file in files])
			self.assertEqual(["1", "1"], [source_file.annual_volume for source_file in files])

	def test_skips_missing_source_folder_with_warning(self):
		with temporary_directory() as temp_dir:
			missing_path = Path(temp_dir) / "missing"

			output = io.StringIO()
			with contextlib.redirect_stdout(output):
				files = scan_source_folders((SourceFolderConfig(path=missing_path, run="Run"),))

			self.assertEqual((), files)
			self.assertIn("source folder not reachable", output.getvalue())


if __name__ == "__main__":
	unittest.main()
