"""Find CBZ files with unreadable image entries and optionally delete them."""

from __future__ import annotations

import argparse
import sys
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
IGNORED_ZIP_NAMES = {"thumbs.db", ".ds_store"}


@dataclass(frozen=True)
class CbzCheckResult:
	path: Path
	is_valid: bool
	reasons: tuple[str, ...]
	image_count: int


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv)
	validator = image_validator(require_pillow=args.require_pillow)
	results = [check_cbz(path, validator) for path in find_cbz_files(args.paths, recursive=args.recursive)]

	if not results:
		print("No CBZ files found.")
		return 0

	bad_results = [result for result in results if not result.is_valid]
	for result in results:
		print_result(result)
		if not result.is_valid and args.apply:
			result.path.unlink()
			print(f"DELETED {result.path}")

	print(f"Summary: checked={len(results)} bad={len(bad_results)} deleted={len(bad_results) if args.apply else 0}")
	if bad_results and not args.apply:
		print("Dry run only. Rerun with --apply to delete bad CBZ files.")
	return 1 if bad_results else 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Check CBZ files for unreadable image entries.")
	parser.add_argument("paths", nargs="+", type=Path, help="CBZ file or folder paths to scan.")
	parser.add_argument("--recursive", action="store_true", help="Scan folders recursively.")
	parser.add_argument("--apply", action="store_true", help="Delete bad CBZ files. Omit for dry run.")
	parser.add_argument("--require-pillow", action="store_true", help="Fail if Pillow is unavailable instead of using fallback checks.")
	return parser.parse_args(argv)


def find_cbz_files(paths: list[Path], *, recursive: bool) -> tuple[Path, ...]:
	found: list[Path] = []
	for path in paths:
		if path.is_file() and path.suffix.casefold() == ".cbz":
			found.append(path)
		elif path.is_dir():
			pattern = "**/*.cbz" if recursive else "*.cbz"
			found.extend(sorted(path.glob(pattern), key=lambda item: str(item).casefold()))
		else:
			print(f"WARN not a CBZ file or folder, skipping: {path}", file=sys.stderr)
	return tuple(found)


def check_cbz(path: Path, validator) -> CbzCheckResult:
	reasons: list[str] = []
	image_count = 0
	try:
		with zipfile.ZipFile(path) as archive:
			bad_member = archive.testzip()
			if bad_member is not None:
				reasons.append(f"zip CRC/read failure at {bad_member}")

			for member in archive.infolist():
				if member.is_dir() or should_ignore_member(member.filename):
					continue
				if Path(member.filename).suffix.casefold() not in IMAGE_SUFFIXES:
					continue
				image_count += 1
				try:
					with archive.open(member) as image_file:
						image_bytes = image_file.read()
					validator(image_bytes, member.filename)
				except Exception as exc:  # noqa: BLE001 - preserve the exact failed member in output.
					reasons.append(f"{member.filename}: {exc}")
	except zipfile.BadZipFile as exc:
		reasons.append(f"not a valid zip/cbz: {exc}")
	except OSError as exc:
		reasons.append(f"could not read file: {exc}")

	if image_count == 0:
		reasons.append("no image files found")

	return CbzCheckResult(path=path, is_valid=not reasons, reasons=tuple(reasons), image_count=image_count)


def should_ignore_member(name: str) -> bool:
	normalized = Path(name).name.casefold()
	return normalized in IGNORED_ZIP_NAMES or name.startswith("__MACOSX/")


def image_validator(*, require_pillow: bool):
	try:
		from PIL import Image
	except ImportError as exc:
		if require_pillow:
			raise RuntimeError("Pillow is required for full image verification. Install with: python -m pip install Pillow") from exc
		print("WARN Pillow is not installed; using basic image signature checks only.", file=sys.stderr)
		return validate_image_signature

	def validate_with_pillow(image_bytes: bytes, member_name: str) -> None:
		with Image.open(BytesIO(image_bytes)) as image:
			image.verify()
		if not image_bytes:
			raise ValueError(f"{member_name} is empty")

	return validate_with_pillow


def validate_image_signature(image_bytes: bytes, member_name: str) -> None:
	if not image_bytes:
		raise ValueError(f"{member_name} is empty")
	if image_bytes.startswith(b"\xff\xd8\xff"):
		if not image_bytes.rstrip().endswith(b"\xff\xd9"):
			raise ValueError("JPEG missing end marker")
		return
	if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
		if b"IEND" not in image_bytes[-32:]:
			raise ValueError("PNG missing IEND chunk near end of file")
		return
	if image_bytes.startswith((b"GIF87a", b"GIF89a")):
		return
	if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
		return
	if image_bytes.startswith(b"BM"):
		return
	if image_bytes.startswith((b"II*\x00", b"MM\x00*")):
		return
	raise ValueError("unknown or unsupported image signature")


def print_result(result: CbzCheckResult) -> None:
	if result.is_valid:
		print(f"OK {result.path} ({result.image_count} images)")
		return

	print(f"BAD {result.path} ({result.image_count} images)")
	for reason in result.reasons:
		print(f"  - {reason}")


if __name__ == "__main__":
	raise SystemExit(main())
