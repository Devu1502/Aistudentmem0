# Session repository shim that forwards calls to Mongo-backed helpers.
from __future__ import annotations

from typing import Any, Dict, List, Optional

from repositories.mongo_repository import (
    delete_session as mongo_delete_session,
    fetch_session_messages as mongo_fetch_session_messages,
    latest_message as mongo_latest_message,
    list_sessions as mongo_list_sessions,
    rename_session as mongo_rename_session,
    update_session_timestamps as mongo_update_session_timestamps,
)


def ensure_table(_conn=None) -> None:
    # Legacy SQLite hook kept for API parity.
    return None


def update_session_timestamps(_conn, session_id: str, timestamp: str, user_id: str) -> None:
    # Keep compatibility with older signatures by passing through.
    mongo_update_session_timestamps(session_id, timestamp, user_id)


def rename_session(_conn, session_id: str, new_title: str, timestamp: str, user_id: str) -> None:
    # Rename or create sessions in Mongo.
    mongo_rename_session(session_id, new_title, timestamp, user_id)


def delete_session(_conn, session_id: str, user_id: str) -> None:
    # Remove a session and its related artifacts.
    mongo_delete_session(session_id, user_id)


def list_sessions(_conn, user_id: str) -> List[Dict[str, Any]]:
    # Read all sessions scoped to one user.
    return mongo_list_sessions(user_id)


def latest_message(_conn, session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    # Grab the most recent teacher/student exchange.
    return mongo_latest_message(session_id, user_id)


def fetch_session_messages(_conn, session_id: str, user_id: str) -> List[Dict[str, Any]]:
    # Return every stored message for UI playback.
    return mongo_fetch_session_messages(session_id, user_id)
