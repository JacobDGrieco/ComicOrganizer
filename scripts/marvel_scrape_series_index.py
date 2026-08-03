"""Scrape Marvel's public series index for Spider-related comic runs."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from db_common import connect_database

DEFAULT_INDEX_URL = "https://www.marvel.com/comics/series"
INCLUDE_PATTERNS = [
    r"spider",
    r"spider-man",
    r"spider-gwen",
    r"spider-girl",
    r"spider-boy",
    r"spider-punk",
    r"spider-ham",
    r"scarlet spider",
    r"venom",
    r"carnage",
    r"symbi",
    r"knull",
    r"queen in black",
    r"silk",
    r"miles morales",
    r"ghost-spider",
]
EXCLUDE_PATTERNS = [
    r"facsimile",
    r"variant",
    r"trade paperback",
    r"hardcover",
    r"omnibus",
    r"epic collection",
    r"masterworks",
    r"complete collection",
    r"modern era epic collection",
    r"digest",
    r"poster",
    r"spanish language",
    r"sketchbook",
    r"premiere comic",
    r"director'?s cut",
]


@dataclass(frozen=True)
class MarvelSeriesCandidate:
    id: str
    title: str
    years: str
    category: str
    publication_type: str
    universe_hint: str
    lead_characters: str
    priority: str
    marvel_url: str
    notes: str


def main() -> int:
    args = parse_args()
    page_html = load_html(args)
    candidates = filter_candidates(parse_series_links(page_html), args)
    if args.apply:
        with connect_database(args.db) as connection:
            for candidate in candidates:
                upsert_run(connection, candidate)
    print(json.dumps([asdict(candidate) for candidate in candidates], indent="\t"))
    print(f"Found {len(candidates)} Marvel series candidates.", file=sys.stderr)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Marvel's public series index for Spider-related runs."
    )
    parser.add_argument(
        "--db", default="projects/spider-man/database/database.db", help="SQLite database path used with --apply."
    )
    parser.add_argument(
        "--url", default=DEFAULT_INDEX_URL, help="Marvel series index URL."
    )
    parser.add_argument(
        "--input-html",
        type=Path,
        help="Use a saved Marvel HTML page instead of fetching.",
    )
    parser.add_argument(
        "--query",
        action="append",
        help="Extra case-insensitive include regex. Can be repeated.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Insert/update matching runs in comic_runs.",
    )
    return parser.parse_args()


def load_html(args: argparse.Namespace) -> str:
    if args.input_html:
        return args.input_html.read_text(encoding="utf-8", errors="replace")
    request = urllib.request.Request(
        args.url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "ComicOrganizer/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        if error.code == 403:
            raise RuntimeError(
                "Marvel blocked the scripted request. Save the page HTML in a browser and rerun with --input-html."
            ) from error
        raise


def parse_series_links(page_html: str) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    link_pattern = re.compile(
        r"<a\b[^>]*href=[\"'](?P<href>/comics/series/(?P<series_id>\d+)/[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in link_pattern.finditer(page_html):
        label = clean_text(match.group("label"))
        if not label:
            continue
        lookahead = page_html[match.end() : match.end() + 200]
        years = years_from_text(label) or years_from_text(clean_text(lookahead)) or ""
        title = re.sub(
            r"\s*\(\d{4}\s*(?:-\s*(?:\d{4}|Present))?\)\s*$", "", label
        ).strip()
        results.append((match.group("series_id"), title, years))
    return dedupe_series(results)


def clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def years_from_text(value: str) -> str | None:
    match = re.search(r"\((\d{4}\s*(?:-\s*(?:\d{4}|Present))?)\)", value, re.IGNORECASE)
    return re.sub(r"\s+", "", match.group(1)) if match else None


def dedupe_series(rows: Iterable[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    seen: set[str] = set()
    deduped: list[tuple[str, str, str]] = []
    for series_id, title, years in rows:
        if series_id in seen:
            continue
        seen.add(series_id)
        deduped.append((series_id, title, years))
    return deduped


def filter_candidates(
    rows: list[tuple[str, str, str]], args: argparse.Namespace
) -> list[MarvelSeriesCandidate]:
    include_patterns = INCLUDE_PATTERNS + (args.query or [])
    candidates: list[MarvelSeriesCandidate] = []
    for series_id, title, years in rows:
        search_text = f"{title} {years}".casefold()
        if not any(
            re.search(pattern, search_text, re.IGNORECASE)
            for pattern in include_patterns
        ):
            continue
        if any(
            re.search(pattern, search_text, re.IGNORECASE)
            for pattern in EXCLUDE_PATTERNS
        ):
            continue
        candidates.append(to_candidate(series_id, title, years))
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.priority,
            candidate.category,
            candidate.title.casefold(),
            candidate.years,
        ),
    )


def to_candidate(series_id: str, title: str, years: str) -> MarvelSeriesCandidate:
    return MarvelSeriesCandidate(
        id=f"MARVEL-SER-{series_id}",
        title=title,
        years=years,
        category=infer_category(title),
        publication_type=infer_publication_type(title),
        universe_hint=infer_universe(title),
        lead_characters=infer_lead_characters(title),
        priority=infer_priority(title),
        marvel_url=f"https://www.marvel.com/comics/series/{series_id}/",
        notes="Imported from Marvel official series index; verify scope before issue import.",
    )


def infer_category(title: str) -> str:
    text = title.casefold()
    if "miles morales" in text:
        return "Miles Morales"
    if "gwen" in text or "ghost-spider" in text:
        return "Spider-Gwen"
    if "2099" in text:
        return "Spider-Man 2099"
    if (
        "venom" in text
        or "carnage" in text
        or "symbi" in text
        or "knull" in text
        or "queen in black" in text
    ):
        return "Symbiote"
    if "ultimate" in text:
        return "Ultimate"
    if "spider-verse" in text or "spider-geddon" in text:
        return "Event"
    return "Core Peter Parker"


def infer_publication_type(title: str) -> str:
    text = title.casefold()
    if "annual" in text:
        return "Annual"
    if "infinity comic" in text or "infinite comic" in text:
        return "Infinity Comic"
    if "special" in text or "super special" in text:
        return "Special"
    if "graphic novel" in text:
        return "Graphic Novel"
    if "alpha" in text or "omega" in text or "one-shot" in text:
        return "One-Shot"
    if "event" in text or "war" in text:
        return "Event"
    return "Ongoing"


def infer_universe(title: str) -> str:
    text = title.casefold()
    if "ultimate" in text:
        return "Ultimate Universe"
    if "noir" in text:
        return "Earth-90214"
    if "2099" in text:
        return "Earth-928 / Earth-2099"
    if "spider-gwen" in text or "ghost-spider" in text:
        return "Earth-65 / Earth-616"
    return "Unknown"


def infer_lead_characters(title: str) -> str:
    text = title.casefold()
    if "miles morales" in text:
        return "Miles Morales"
    if "gwen" in text or "ghost-spider" in text:
        return "Gwen Stacy"
    if "2099" in text or "miguel" in text:
        return "Miguel O'Hara"
    if "venom" in text:
        return "Venom cast"
    if "carnage" in text:
        return "Carnage"
    if "silk" in text:
        return "Cindy Moon"
    return "Peter Parker"


def infer_priority(title: str) -> str:
    text = title.casefold()
    if (
        "amazing spider-man" in text
        or "spectacular spider-man" in text
        or "ultimate spider-man" in text
    ):
        return "P0"
    if (
        "miles morales" in text
        or "spider-gwen" in text
        or "venom" in text
        or "spider-verse" in text
    ):
        return "P1"
    return "P2"


def upsert_run(connection, candidate: MarvelSeriesCandidate) -> None:
    connection.execute(
        """
		INSERT INTO comic_runs (
			id, title, volume, years, category, publication_type, universe_hint,
			lead_characters, priority, marvel_url, notes
		)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET
			title = excluded.title,
			years = excluded.years,
			category = excluded.category,
			publication_type = excluded.publication_type,
			universe_hint = excluded.universe_hint,
			lead_characters = excluded.lead_characters,
			priority = excluded.priority,
			marvel_url = excluded.marvel_url,
			notes = excluded.notes
		""",
        (
            candidate.id,
            candidate.title,
            "",
            candidate.years,
            candidate.category,
            candidate.publication_type,
            candidate.universe_hint,
            candidate.lead_characters,
            candidate.priority,
            candidate.marvel_url,
            candidate.notes,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
