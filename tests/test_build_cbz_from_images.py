import sys
import unittest
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from build_cbz_from_images import main
from helpers import temporary_directory


class BuildCbzFromImagesTests(unittest.TestCase):
	def test_builds_cbz_from_local_images_in_natural_order(self):
		with temporary_directory() as directory:
			base_path = Path(directory)
			image_folder = base_path / "pages"
			output_folder = base_path / "out"
			image_folder.mkdir()
			(image_folder / "page10.jpg").write_bytes(b"ten")
			(image_folder / "page2.jpg").write_bytes(b"two")
			(image_folder / "page1.png").write_bytes(b"one")

			exit_code = main(
				[
					"--images",
					str(image_folder),
					"--output-folder",
					str(output_folder),
					"--run",
					"The Amazing Spider-Man",
					"--volume",
					"1",
					"--issue",
					"12",
				]
			)

			output_path = output_folder / "The Amazing Spider-Man v1 12.cbz"
			self.assertEqual(0, exit_code)
			self.assertTrue(output_path.exists())
			with zipfile.ZipFile(output_path) as archive:
				self.assertEqual(["0001.png", "0002.jpg", "0003.jpg"], archive.namelist())
				self.assertEqual(b"one", archive.read("0001.png"))
				self.assertEqual(b"two", archive.read("0002.jpg"))
				self.assertEqual(b"ten", archive.read("0003.jpg"))

	def test_refuses_to_overwrite_without_force(self):
		with temporary_directory() as directory:
			base_path = Path(directory)
			image_folder = base_path / "pages"
			output_folder = base_path / "out"
			image_folder.mkdir()
			output_folder.mkdir()
			(image_folder / "page1.jpg").write_bytes(b"one")
			(output_folder / "Run v1 1.cbz").write_bytes(b"existing")

			with self.assertRaises(RuntimeError):
				main(
					[
						"--images",
						str(image_folder),
						"--output-folder",
						str(output_folder),
						"--run",
						"Run",
						"--volume",
						"1",
						"--issue",
						"1",
					]
				)


if __name__ == "__main__":
	unittest.main()
