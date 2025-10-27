from __future__ import annotations

from typing import List, Optional

import sqlite3

from config.settings import settings

SESSION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS session_meta (
    session_id TEXT PRIMARY KEY
);
"""

ALTER_COLUMNS = {
    "title": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(SESSION_TABLE_SQL)
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(session_meta)")}
    for column, col_type in ALTER_COLUMNS.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE session_meta ADD COLUMN {column} {col_type}")
    conn.commit()


def update_session_timestamps(conn: sqlite3.Connection, session_id: str, timestamp: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO session_meta (session_id, created_at) VALUES (?, ?)",
        (session_id, timestamp),
    )
    conn.execute(
        "UPDATE session_meta SET created_at=COALESCE(created_at, ?), updated_at=? WHERE session_id=?",
        (timestamp, timestamp, session_id),
    )
    conn.commit()


def rename_session(conn: sqlite3.Connection, session_id: str, new_title: str, timestamp: str) -> None:
    conn.execute(
        """
        INSERT INTO session_meta (session_id, title, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            title=excluded.title,
            updated_at=excluded.updated_at
        """,
        (session_id, new_title, timestamp, timestamp),
    )
    conn.commit()


def delete_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM session_meta WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM chat_history WHERE session_id=?", (session_id,))
    conn.commit()


def list_sessions(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT ch.session_id,
               COALESCE(sm.title, '') AS title,
               MAX(ch.timestamp) AS last_time
        FROM chat_history ch
        LEFT JOIN session_meta sm ON sm.session_id = ch.session_id
        GROUP BY ch.session_id
        ORDER BY last_time DESC
        """
    )
    return cur.fetchall()


def latest_message(conn: sqlite3.Connection, session_id: str) -> Optional[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT user_input, ai_output, timestamp
        FROM chat_history
        WHERE session_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (session_id,),
    )
    return cur.fetchone()


def fetch_session_messages(conn: sqlite3.Connection, session_id: str) -> List[sqlite3.Row]:
    cur = conn.execute(
        "SELECT user_input, ai_output, timestamp FROM chat_history WHERE session_id=? ORDER BY id ASC",
        (session_id,),
    )
    return cur.fetchall()
