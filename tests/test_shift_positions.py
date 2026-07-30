import unittest
from pathlib import Path

from helpers import temporary_directory
from shift_positions import ShiftPositionsError, apply_shift, plan_shift


class ShiftPositionsTests(unittest.TestCase):
	def test_plans_positive_shift_from_selected_file_onward(self):
		with temporary_directory() as temp_dir:
			folder = Path(temp_dir)
			_create_files(folder, "0001 - A.cbz", "0004 - C.cbz", "0005 - D.cbz")

			plan = plan_shift(folder, "0004 - C.cbz")

			self.assertEqual(
				[
					("0005 - D.cbz", "0006 - D.cbz"),
					("0004 - C.cbz", "0005 - C.cbz"),
				],
				[(item.source_path.name, item.destination_path.name) for item in plan],
			)

	def test_applies_positive_shift_without_overwriting(self):
		with temporary_directory() as temp_dir:
			folder = Path(temp_dir)
			_create_files(folder, "0004 - C.cbz", "0005 - D.cbz")

			apply_shift(plan_shift(folder, "0004 - C.cbz"))

			self.assertFalse((folder / "0004 - C.cbz").exists())
			self.assertTrue((folder / "0005 - C.cbz").exists())
			self.assertTrue((folder / "0006 - D.cbz").exists())

	def test_rejects_target_collision_outside_shifted_range(self):
		with temporary_directory() as temp_dir:
			folder = Path(temp_dir)
			_create_files(folder, "0003 - Existing.cbz", "0004 - C.cbz")

			with self.assertRaises(ShiftPositionsError):
				plan_shift(folder, "0004 - C.cbz", increment=-1)

	def test_rejects_zero_increment(self):
		with temporary_directory() as temp_dir:
			folder = Path(temp_dir)
			_create_files(folder, "0004 - C.cbz")

			with self.assertRaises(ShiftPositionsError):
				plan_shift(folder, "0004 - C.cbz", increment=0)


def _create_files(folder: Path, *names: str) -> None:
	for name in names:
		(folder / name).write_bytes(b"comic")


if __name__ == "__main__":
	unittest.main()
