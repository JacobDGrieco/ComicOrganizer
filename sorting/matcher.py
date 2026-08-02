"""Match parsed source files to the database-derived reading order."""

from __future__ import annotations

from .issue_numbers import comparable_issue_number
from .models import DuplicateCandidate, MatchedComic, MatchResult, ParsedCandidate, ReadingOrderEntry


def match_candidates(
	reading_order: tuple[ReadingOrderEntry, ...],
	candidates: tuple[ParsedCandidate, ...],
) -> MatchResult:
	"""Match source candidates to reading-order entries without trusting filenames for output names."""
	sorted_candidates = tuple(
		sorted(candidates, key=lambda candidate: (candidate.source_order, candidate.raw_name.casefold()))
	)
	matches: list[MatchedComic] = []
	unmatched_entries: list[ReadingOrderEntry] = []
	duplicate_candidates: list[DuplicateCandidate] = []
	used_candidate_ids: set[int] = set()

	for entry in reading_order:
		entry_candidates = [
			candidate
			for candidate in sorted_candidates
			if id(candidate) not in used_candidate_ids and candidate_matches_entry(candidate, entry)
		]
		if not entry_candidates:
			unmatched_entries.append(entry)
			continue

		winner = entry_candidates[0]
		used_candidate_ids.add(id(winner))
		matches.append(
			MatchedComic(
				position=entry.position,
				run=entry.run,
				issue_label=entry.issue_label,
				canonical_name=canonical_filename(entry, winner),
				source_path=winner.source_path,
				is_annual=winner.is_annual,
			)
		)

		for duplicate in entry_candidates[1:]:
			used_candidate_ids.add(id(duplicate))
			duplicate_candidates.append(DuplicateCandidate(entry=entry, winner=winner, duplicate=duplicate))

	unmatched_candidates = tuple(
		candidate
		for candidate in candidates
		if id(candidate) not in used_candidate_ids
	)

	return MatchResult(
		matches=tuple(sorted(matches, key=lambda match: match.position)),
		unmatched_entries=tuple(unmatched_entries),
		unmatched_candidates=unmatched_candidates,
		duplicate_candidates=tuple(duplicate_candidates),
	)


def canonical_filename(entry: ReadingOrderEntry, candidate: ParsedCandidate) -> str:
	return f"{entry.position:05d} - {candidate.source_path.name}"


def entry_match_key(entry: ReadingOrderEntry) -> tuple[str, str, str]:
	return (entry.run.casefold(), entry.volume, comparable_issue_number(entry.issue_label))


def candidate_match_key(candidate: ParsedCandidate) -> tuple[str, str, str]:
	return (candidate.run.casefold(), candidate.volume, comparable_issue_number(candidate.issue_number))


def candidate_matches_entry(candidate: ParsedCandidate, entry: ReadingOrderEntry) -> bool:
	if candidate.run.casefold() != entry.run.casefold():
		return False
	if candidate.volume != entry.volume:
		return False
	if candidate.annual_release_year:
		return entry.release_date.startswith(candidate.annual_release_year)
	if candidate.is_annual and candidate.annual_start_year and entry.run_start_year and entry.run_start_year != candidate.annual_start_year:
		return False
	return comparable_issue_number(candidate.issue_number) == comparable_issue_number(entry.issue_label)
