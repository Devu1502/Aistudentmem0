from __future__ import annotations

from __future__ import annotations

from typing import List, Tuple

from repositories.mongo_repository import fetch_history as mongo_fetch_history
from repositories.mongo_repository import insert_message as mongo_insert_message


def ensure_table(_conn=None) -> None:
    return None


def fetch_history(_conn, session_id: str) -> List[Tuple[str, str]]:
    return mongo_fetch_history(session_id)


def insert_message(_conn, session_id: str, user_input: str, ai_output: str, timestamp: str) -> None:
    mongo_insert_message(session_id, user_input, ai_output, timestamp)
