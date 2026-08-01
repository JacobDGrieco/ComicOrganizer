"""Scan configured source folders for CBZ files."""

from __future__ import annotations

from .models import SourceFile, SourceFolderConfig


def scan_source_folders(source_folders: tuple[SourceFolderConfig, ...]) -> tuple[SourceFile, ...]:
	files: list[SourceFile] = []
	for source_order, source_folder in enumerate(source_folders):
		if not source_folder.path.is_dir():
			continue

		for path in sorted(source_folder.path.iterdir(), key=lambda current_path: current_path.name.casefold()):
			if path.is_file() and path.suffix.casefold() == ".cbz":
				files.append(
					SourceFile(
						path=path,
						run=source_folder.run,
						volume=source_folder.volume,
						source_order=source_order,
						annual_run=source_folder.annual_run,
						annual_volume=source_folder.annual_volume,
						annual_start_year=source_folder.annual_start_year,
						special_run=source_folder.special_run,
						special_volume=source_folder.special_volume,
						issue_aliases=source_folder.issue_aliases,
					)
				)

	return tuple(files)
