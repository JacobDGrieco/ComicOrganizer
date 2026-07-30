import json
import unittest
from pathlib import Path

from config import ConfigError, load_config
from helpers import temporary_directory


class ConfigTests(unittest.TestCase):
	def test_loads_valid_config(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			reading_order_path = base_path / "reading_order.json"
			destination_path = base_path / "destination"
			source_path = base_path / "source"
			reading_order_path.write_text('{"entries": []}', encoding="utf-8")
			destination_path.mkdir()
			source_path.mkdir()
			config_path = base_path / "config.json"
			config_path.write_text(
				json.dumps(
					{
						"reading_order_path": str(reading_order_path),
						"destination_folder": str(destination_path),
						"source_folders": [
							{
								"path": str(source_path),
								"run": "The Amazing Spider-Man",
								"output_name": "Amazing Spider-Man",
								"volume": 2,
								"annual_run": "Amazing Spider-Man Annual",
								"annual_output_name": "Amazing Spider-Man Annual",
								"annual_volume": 1,
							}
						],
						"issue_overrides": {"Amazing Fantasy": {"1": "15"}},
					}
				),
				encoding="utf-8",
			)

			config = load_config(config_path)

			self.assertEqual(reading_order_path, config.reading_order_path)
			self.assertEqual(destination_path, config.destination_folder)
			self.assertEqual("The Amazing Spider-Man", config.source_folders[0].run)
			self.assertEqual("Amazing Spider-Man", config.source_folders[0].output_name)
			self.assertEqual("2", config.source_folders[0].volume)
			self.assertEqual("Amazing Spider-Man Annual", config.source_folders[0].annual_run)
			self.assertEqual("Amazing Spider-Man Annual", config.source_folders[0].annual_output_name)
			self.assertEqual("1", config.source_folders[0].annual_volume)
			self.assertEqual({"Amazing Fantasy": {"1": "15"}}, config.issue_overrides)

	def test_output_name_defaults_to_run(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			reading_order_path = base_path / "reading_order.json"
			destination_path = base_path / "destination"
			source_path = base_path / "source"
			reading_order_path.write_text('{"entries": []}', encoding="utf-8")
			destination_path.mkdir()
			source_path.mkdir()
			config_path = base_path / "config.json"
			config_path.write_text(
				json.dumps(
					{
						"reading_order_path": str(reading_order_path),
						"destination_folder": str(destination_path),
						"source_folders": [{"path": str(source_path), "run": "The Amazing Spider-Man"}],
						"issue_overrides": {},
					}
				),
				encoding="utf-8",
			)

			config = load_config(config_path)

			self.assertEqual("The Amazing Spider-Man", config.source_folders[0].output_name)
			self.assertEqual("The Amazing Spider-Man Annual", config.source_folders[0].annual_run)
			self.assertEqual("The Amazing Spider-Man Annual", config.source_folders[0].annual_output_name)

	def test_allows_missing_source_folder(self):
		with temporary_directory() as temp_dir:
			base_path = Path(temp_dir)
			reading_order_path = base_path / "reading_order.json"
			destination_path = base_path / "destination"
			reading_order_path.write_text('{"entries": []}', encoding="utf-8")
			destination_path.mkdir()
			config_path = base_path / "config.json"
			config_path.write_text(
				json.dumps(
					{
						"reading_order_path": str(reading_order_path),
						"destination_folder": str(destination_path),
						"source_folders": [{"path": str(base_path / "missing"), "run": "The Amazing Spider-Man"}],
						"issue_overrides": {},
					}
				),
				encoding="utf-8",
			)

			config = load_config(config_path)

			self.assertEqual(base_path / "missing", config.source_folders[0].path)


if __name__ == "__main__":
	unittest.main()
