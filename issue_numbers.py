"""Issue-number normalization shared by spreadsheet and filename matching."""

from __future__ import annotations

import re


_ISSUE_PREFIX_RE = re.compile(r"^\s*(?:issue\s*)?#\s*", re.IGNORECASE)
_ISSUE_WORD_RE = re.compile(r"^\s*issue\s+", re.IGNORECASE)
_INTEGER_RE = re.compile(r"^[+-]?\d+$")


def normalize_issue_label(value: object) -> str:
	"""Return a display-ready issue label without a leading Issue/# prefix."""
	if value is None:
		return ""

	if isinstance(value, float) and value.is_integer():
		return str(int(value))

	text = str(value).strip()
	text = _ISSUE_PREFIX_RE.sub("", text)
	text = _ISSUE_WORD_RE.sub("", text)
	text = text.strip()
	if _INTEGER_RE.match(text):
		return str(int(text))

	return text


def comparable_issue_number(value: object) -> str:
	"""Return a stable comparison key, stripping leading zeroes for integers."""
	label = normalize_issue_label(value)
	if _INTEGER_RE.match(label):
		return str(int(label))

	return label.casefold()


def normalize_volume_label(value: object) -> str:
	"""Return a stable volume label for spreadsheet/config/filename matching."""
	if value is None:
		return ""

	if isinstance(value, float) and value.is_integer():
		return str(int(value))

	text = str(value).strip()
	if _INTEGER_RE.match(text):
		return str(int(text))

	return text.casefold()
