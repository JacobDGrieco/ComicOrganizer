"""Match parsed source files to the configured reading order."""

from __future__ import annotations

from .issue_numbers import comparable_issue_number
from .models import DuplicateCandidate, MatchedComic, MatchResult, ParsedCandidate, ReadingOrderEntry


def match_candidates(
	reading_order: tuple[ReadingOrderEntry, ...],
	candidates: tuple[ParsedCandidate, ...],
) -> MatchResult:
	candidates_by_key: dict[tuple[str, str, str], list[ParsedCandidate]] = {}
	for candidate in sorted(candidates, key=lambda current_candidate: (current_candidate.source_order, current_candidate.raw_name.casefold())):
		candidates_by_key.setdefault(candidate_match_key(candidate), []).append(candidate)

	reading_keys = {entry_match_key(entry) for entry in reading_order}
	matches: list[MatchedComic] = []
	unmatched_entries: list[ReadingOrderEntry] = []
	duplicate_candidates: list[DuplicateCandidate] = []
	used_candidate_ids: set[int] = set()

	for entry in reading_order:
		entry_candidates = candidates_by_key.get(entry_match_key(entry), [])
		if not entry_candidates:
			unmatched_entries.append(entry)
			continue

		winner = entry_candidates[0]
		used_candidate_ids.add(id(winner))
		output_name = winner.output_name or winner.run
		is_annual = winner.is_annual or _is_annual_name(winner.run) or _is_annual_name(output_name)
		matches.append(
			MatchedComic(
				position=entry.position,
				run=output_name,
				issue_label=entry.issue_label,
				canonical_name=canonical_filename(entry, output_name),
				source_path=winner.source_path,
				is_annual=is_annual,
			)
		)

		for duplicate in entry_candidates[1:]:
			used_candidate_ids.add(id(duplicate))
			duplicate_candidates.append(DuplicateCandidate(entry=entry, winner=winner, duplicate=duplicate))

	unmatched_candidates = tuple(
		candidate
		for candidate in candidates
		if id(candidate) not in used_candidate_ids and candidate_match_key(candidate) not in reading_keys
	)

	return MatchResult(
		matches=tuple(sorted(matches, key=lambda match: match.position)),
		unmatched_entries=tuple(unmatched_entries),
		unmatched_candidates=unmatched_candidates,
		duplicate_candidates=tuple(duplicate_candidates),
	)


def canonical_filename(entry: ReadingOrderEntry, output_name: str | None = None) -> str:
	run_name = output_name or entry.run
	return f"{entry.position:04d} - {run_name} #{entry.issue_label}.cbz"


def entry_match_key(entry: ReadingOrderEntry) -> tuple[str, str, str]:
	return (entry.run.casefold(), entry.volume, comparable_issue_number(entry.issue_label))


def candidate_match_key(candidate: ParsedCandidate) -> tuple[str, str, str]:
	return (candidate.run.casefold(), candidate.volume, comparable_issue_number(candidate.issue_number))


def _is_annual_name(run_name: str) -> bool:
	return run_name.casefold().endswith(" annual")
