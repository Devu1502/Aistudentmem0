# Thin wrapper around SQLite for scripts that still rely on it.
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Generator

from config.settings import settings


# Apply shared connection tweaks (row factory, etc.).
def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row


@contextmanager
# Yield SQLite connections and clean them up automatically.
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    _configure_connection(conn)
    try:
        yield conn
    finally:
        conn.close()
