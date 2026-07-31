"""Scan configured source folders for CBZ files."""

from __future__ import annotations

from colorama import Fore, Style

from .models import SourceFile, SourceFolderConfig


def scan_source_folders(source_folders: tuple[SourceFolderConfig, ...]) -> tuple[SourceFile, ...]:
	files: list[SourceFile] = []
	for source_order, source_folder in enumerate(source_folders):
		if not source_folder.path.is_dir():
			print(f"{Fore.YELLOW}WARN{Style.RESET_ALL} source folder not reachable, skipping: {source_folder.path}")
			continue

		for path in sorted(source_folder.path.iterdir(), key=lambda current_path: current_path.name.casefold()):
			if path.is_file() and path.suffix.casefold() == ".cbz":
				files.append(
					SourceFile(
						path=path,
						run=source_folder.run,
						source_order=source_order,
						output_name=source_folder.output_name,
						volume=source_folder.volume,
						annual_run=source_folder.annual_run,
						annual_output_name=source_folder.annual_output_name,
						annual_volume=source_folder.annual_volume,
					)
				)

	return tuple(files)
