"""Search Marvel Metadata API series names locally after paginated fetch."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request


API_BASE_URL = "https://marvel.emreparker.com/v1"


def main() -> int:
	args = parse_args()
	query = args.query.casefold()
	offset = 0
	matches = []
	while True:
		url = f"{API_BASE_URL}/series?limit=200&offset={offset}"
		payload = fetch_json(url)
		for item in payload.get("items", []):
			if query in item.get("name", "").casefold():
				matches.append(item)
		if not payload.get("has_next"):
			break
		offset += int(payload.get("limit") or 200)
		time.sleep(args.delay_seconds)

	print(json.dumps(matches, indent="\t"))
	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Find Marvel Metadata API series IDs.")
	parser.add_argument("query", help="Case-insensitive substring to search for.")
	parser.add_argument("--delay-seconds", type=float, default=0.25, help="Delay between page requests.")
	return parser.parse_args()


def fetch_json(url: str):
	request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ComicOrganizer/0.1"})
	with urllib.request.urlopen(request, timeout=30) as response:
		return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
	raise SystemExit(main())
