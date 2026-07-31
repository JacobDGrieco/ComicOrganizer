"""Build a CBZ from local images or authorized direct image URLs."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class ImageInput:
	name: str
	bytes: bytes
	suffix: str


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv)
	if args.images and args.manifest:
		raise RuntimeError("Use either --images or --manifest, not both.")
	if not args.images and not args.manifest:
		raise RuntimeError("Provide --images for a local folder or --manifest for authorized direct image URLs.")

	images = read_local_images(args.images) if args.images else download_manifest_images(args.manifest)
	if not images:
		raise RuntimeError("No image files found.")

	output_path = output_cbz_path(args)
	if output_path.exists() and not args.force:
		raise RuntimeError(f"Output already exists: {output_path}. Use --force to overwrite.")

	output_path.parent.mkdir(parents=True, exist_ok=True)
	with tempfile.NamedTemporaryFile(delete=False, suffix=".cbz", dir=output_path.parent) as temp_file:
		temp_path = Path(temp_file.name)

	try:
		write_cbz(temp_path, images)
		temp_path.replace(output_path)
	finally:
		temp_path.unlink(missing_ok=True)

	print(f"Created {output_path} ({len(images)} images)")
	return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Build a CBZ from image files.")
	parser.add_argument("--images", type=Path, help="Folder containing page images for one issue.")
	parser.add_argument("--manifest", type=Path, help="Text or JSON file containing authorized direct image URLs.")
	parser.add_argument("--output-folder", required=True, type=Path, help="Folder where the CBZ should be written.")
	parser.add_argument("--run", required=True, help="Comic run name used in the output filename.")
	parser.add_argument("--volume", default="1", help="Volume label used in the output filename.")
	parser.add_argument("--issue", required=True, help="Issue number used in the output filename.")
	parser.add_argument("--output-name", help="Optional filename run name override.")
	parser.add_argument("--force", action="store_true", help="Overwrite an existing CBZ.")
	return parser.parse_args(argv)


def read_local_images(folder: Path) -> list[ImageInput]:
	if not folder.is_dir():
		raise RuntimeError(f"Image folder does not exist: {folder}")
	images: list[ImageInput] = []
	for path in sorted(folder.iterdir(), key=lambda item: natural_sort_key(item.name)):
		if not path.is_file() or path.suffix.casefold() not in IMAGE_SUFFIXES:
			continue
		image_bytes = path.read_bytes()
		validate_nonempty_image(path.name, image_bytes)
		images.append(ImageInput(name=path.name, bytes=image_bytes, suffix=normalized_suffix(path.suffix)))
	return images


def download_manifest_images(path: Path) -> list[ImageInput]:
	urls = read_manifest_urls(path)
	images: list[ImageInput] = []
	for index, url in enumerate(urls, start=1):
		image_bytes, suffix = download_image(url)
		validate_nonempty_image(url, image_bytes)
		images.append(ImageInput(name=f"{index:04d}{suffix}", bytes=image_bytes, suffix=suffix))
	return images


def read_manifest_urls(path: Path) -> list[str]:
	if not path.is_file():
		raise RuntimeError(f"Manifest does not exist: {path}")
	text = path.read_text(encoding="utf-8-sig").strip()
	if not text:
		return []
	if text.startswith("["):
		raw_urls = json.loads(text)
		if not isinstance(raw_urls, list):
			raise RuntimeError("JSON manifest must be an array of URL strings.")
		return [str(url).strip() for url in raw_urls if str(url).strip()]
	return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def download_image(url: str) -> tuple[bytes, str]:
	request = urllib.request.Request(
		url,
		headers={
			"Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
			"User-Agent": "ComicOrganizer/0.1",
		},
	)
	try:
		with urllib.request.urlopen(request, timeout=30) as response:
			content_type = response.headers.get("content-type", "")
			image_bytes = response.read()
	except urllib.error.HTTPError as exc:
		raise RuntimeError(f"Could not download {url}: HTTP {exc.code}") from exc
	except urllib.error.URLError as exc:
		raise RuntimeError(f"Could not download {url}: {exc}") from exc

	return image_bytes, suffix_from_url_or_content_type(url, content_type)


def suffix_from_url_or_content_type(url: str, content_type: str) -> str:
	suffix = normalized_suffix(Path(urllib.request.url2pathname(url.split("?", 1)[0])).suffix)
	if suffix in IMAGE_SUFFIXES:
		return suffix
	content_type = content_type.split(";", 1)[0].strip().casefold()
	return {
		"image/jpeg": ".jpg",
		"image/png": ".png",
		"image/gif": ".gif",
		"image/webp": ".webp",
		"image/bmp": ".bmp",
		"image/tiff": ".tif",
	}.get(content_type, ".jpg")


def normalized_suffix(suffix: str) -> str:
	suffix = suffix.casefold()
	return ".jpg" if suffix == ".jpeg" else suffix


def validate_nonempty_image(name: str, image_bytes: bytes) -> None:
	if not image_bytes:
		raise RuntimeError(f"Image is empty: {name}")


def write_cbz(path: Path, images: list[ImageInput]) -> None:
	with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
		for index, image in enumerate(images, start=1):
			archive.writestr(f"{index:04d}{image.suffix}", image.bytes)


def output_cbz_path(args: argparse.Namespace) -> Path:
	run_name = args.output_name or args.run
	filename = f"{safe_filename(run_name)} v{args.volume} {safe_filename(args.issue)}.cbz"
	return args.output_folder / filename


def safe_filename(value: str) -> str:
	value = re.sub(r'[<>:"/\\|?*]+', " ", value)
	value = re.sub(r"\s+", " ", value).strip()
	return value.rstrip(". ")


def natural_sort_key(value: str) -> tuple[object, ...]:
	parts: list[object] = []
	for part in re.split(r"(\d+)", value.casefold()):
		parts.append(int(part) if part.isdigit() else part)
	return tuple(parts)


if __name__ == "__main__":
	raise SystemExit(main())
