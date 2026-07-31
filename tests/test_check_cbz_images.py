import sys
import unittest
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from check_cbz_images import check_cbz, find_cbz_files, main, validate_image_signature
from helpers import temporary_directory


class CheckCbzImagesTests(unittest.TestCase):
	def test_check_cbz_accepts_valid_signature(self):
		with temporary_directory() as directory:
			path = Path(directory) / "valid.cbz"
			with zipfile.ZipFile(path, "w") as archive:
				archive.writestr("page001.jpg", b"\xff\xd8\xffvalid-image\xff\xd9")

			result = check_cbz(path, validate_image_signature)

		self.assertTrue(result.is_valid)
		self.assertEqual(1, result.image_count)

	def test_check_cbz_rejects_unopenable_image(self):
		with temporary_directory() as directory:
			path = Path(directory) / "bad.cbz"
			with zipfile.ZipFile(path, "w") as archive:
				archive.writestr("page001.jpg", b"not an image")

			result = check_cbz(path, validate_image_signature)

		self.assertFalse(result.is_valid)
		self.assertIn("unknown or unsupported image signature", result.reasons[0])

	def test_main_dry_run_does_not_delete_bad_cbz(self):
		with temporary_directory() as directory:
			path = Path(directory) / "bad.cbz"
			with zipfile.ZipFile(path, "w") as archive:
				archive.writestr("page001.jpg", b"not an image")

			exit_code = main([str(path)])

			self.assertEqual(1, exit_code)
			self.assertTrue(path.exists())

	def test_main_apply_deletes_bad_cbz(self):
		with temporary_directory() as directory:
			path = Path(directory) / "bad.cbz"
			with zipfile.ZipFile(path, "w") as archive:
				archive.writestr("page001.jpg", b"not an image")

			exit_code = main([str(path), "--apply"])

			self.assertEqual(1, exit_code)
			self.assertFalse(path.exists())

	def test_find_cbz_files_supports_recursive_scan(self):
		with temporary_directory() as directory:
			base_path = Path(directory)
			nested_path = base_path / "nested"
			nested_path.mkdir()
			(base_path / "root.cbz").write_bytes(b"")
			(nested_path / "nested.cbz").write_bytes(b"")

			flat = find_cbz_files([base_path], recursive=False)
			recursive = find_cbz_files([base_path], recursive=True)

		self.assertEqual(1, len(flat))
		self.assertEqual(2, len(recursive))


if __name__ == "__main__":
	unittest.main()
