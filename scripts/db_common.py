"""Shared SQLite helpers for Spider-Man reading-list scripts."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_database(database_path: str | Path) -> sqlite3.Connection:
	"""Open a SQLite database with foreign-key checks enabled."""
	connection = sqlite3.connect(database_path)
	connection.row_factory = sqlite3.Row
	connection.execute("PRAGMA foreign_keys = ON")
	return connection


def project_root() -> Path:
	return Path(__file__).resolve().parents[1]
