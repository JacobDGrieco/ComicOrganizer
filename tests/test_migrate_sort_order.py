import json
import unittest
from pathlib import Path

from helpers import temporary_directory
from migrate_sort_order import MigrationError, apply_migration, plan_migration


class MigrateSortOrderTests(unittest.TestCase):
	def test_plans_migration_using_old_sheet_position_reference(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			folder = base_path / "destination"
			folder.mkdir()
			_create_files(folder, "0001 - Run #1.cbz", "0002 - Run #2.cbz")
			old_order = base_path / "old.json"
			new_order = base_path / "new.json"
			_create_reading_order(old_order, [("Run", 1, "#1"), ("Run", 1, "#2")])
			_create_reading_order(new_order, [("Run", 1, "#2"), ("Run", 1, "#1")])

			plan = plan_migration(folder, new_order, old_reading_order_path=old_order)

			self.assertEqual(
				[
					("0001 - Run #1.cbz", "0002 - Run #1.cbz"),
					("0002 - Run #2.cbz", "0001 - Run #2.cbz"),
				],
				[(item.source_path.name, item.destination_path.name) for item in plan.items],
			)
			self.assertEqual((), plan.warnings)

	def test_applies_migration_with_swapped_positions(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			folder = base_path / "destination"
			folder.mkdir()
			_create_files(folder, "0001 - Run #1.cbz", "0002 - Run #2.cbz")
			old_order = base_path / "old.json"
			new_order = base_path / "new.json"
			_create_reading_order(old_order, [("Run", 1, "#1"), ("Run", 1, "#2")])
			_create_reading_order(new_order, [("Run", 1, "#2"), ("Run", 1, "#1")])

			apply_migration(plan_migration(folder, new_order, old_reading_order_path=old_order))

			self.assertTrue((folder / "0001 - Run #2.cbz").exists())
			self.assertTrue((folder / "0002 - Run #1.cbz").exists())

	def test_plans_migration_by_decoding_filename_when_unambiguous(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			folder = base_path / "destination"
			folder.mkdir()
			_create_files(folder, "0099 - Run #2.cbz")
			new_order = base_path / "new.json"
			_create_reading_order(new_order, [("Run", 1, "#1"), ("Run", 1, "#2")])

			plan = plan_migration(folder, new_order)

			self.assertEqual("0002 - Run #2.cbz", plan.items[0].destination_path.name)
			self.assertEqual((), plan.warnings)

	def test_filename_decode_warns_when_new_sheet_match_is_ambiguous(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			folder = base_path / "destination"
			folder.mkdir()
			_create_files(folder, "0099 - Run #1.cbz")
			new_order = base_path / "new.json"
			_create_reading_order(new_order, [("Run", 1, "#1"), ("Run", 2, "#1")])

			plan = plan_migration(folder, new_order)

			self.assertEqual((), plan.items)
			self.assertIn("ambiguous", plan.warnings[0])

	def test_rejects_duplicate_target_positions(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			folder = base_path / "destination"
			folder.mkdir()
			_create_files(folder, "0001 - Run #1.cbz", "0002 - Run #2.cbz")
			old_order = base_path / "old.json"
			new_order = base_path / "new.json"
			_create_reading_order(old_order, [("Run", 1, "#1"), ("Run", 1, "#2")])
			_create_reading_order(new_order, [("Run", 1, "#1"), ("Run", 1, "#1")])

			with self.assertRaises(MigrationError):
				plan_migration(folder, new_order, old_reading_order_path=old_order)


def _create_files(folder: Path, *names: str) -> None:
	for name in names:
		(folder / name).write_bytes(b"comic")


def _create_reading_order(path: Path, entries: list[tuple[str, int, str]]) -> None:
	path.write_text(
		json.dumps({"entries": [{"run": run, "volume": volume, "issue": issue} for run, volume, issue in entries]}),
		encoding="utf-8",
	)


if __name__ == "__main__":
	unittest.main()
