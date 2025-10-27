from __future__ import annotations

from typing import Iterable, List, Tuple

import sqlite3


CHAT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    user_input TEXT,
    ai_output TEXT,
    timestamp TEXT
);
"""


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(CHAT_TABLE_SQL)
    conn.commit()


def fetch_history(conn: sqlite3.Connection, session_id: str) -> List[Tuple[str, str]]:
    cur = conn.execute(
        "SELECT user_input, ai_output FROM chat_history WHERE session_id=? ORDER BY id ASC;",
        (session_id,),
    )
    return [(row[0], row[1]) for row in cur.fetchall() if row[0] or row[1]]


def insert_message(
    conn: sqlite3.Connection,
    session_id: str,
    user_input: str,
    ai_output: str,
    timestamp: str,
) -> None:
    conn.execute(
        "INSERT INTO chat_history (session_id, user_input, ai_output, timestamp) VALUES (?, ?, ?, ?);",
        (session_id, user_input, ai_output, timestamp),
    )
    conn.commit()
