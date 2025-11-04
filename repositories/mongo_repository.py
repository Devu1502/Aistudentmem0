from __future__ import annotations

import os
from datetime import datetime
import math
from typing import Any, Dict, List, Optional
from pymongo import ASCENDING, DESCENDING, MongoClient

MONGO_URI = os.getenv("MONGODB_URI")
if not MONGO_URI:
    raise RuntimeError("MONGODB_URI environment variable is required for MongoDB repository.")

client = MongoClient(MONGO_URI)
db = client["AIBuddy"]
chat_collection = db["chat_messages"]
session_collection = db["sessions"]


def _ensure_indexes() -> None:
    chat_collection.create_index([("session_id", ASCENDING), ("timestamp", DESCENDING)])
    session_collection.create_index([("session_id", ASCENDING)], unique=True)


_ensure_indexes()


def insert_message(session_id: str, user_input: str, ai_output: str, timestamp: Optional[str] = None) -> Dict[str, Any]:
    ts = timestamp or datetime.utcnow().isoformat()
    doc = {
        "session_id": session_id,
        "user_input": user_input,
        "ai_output": ai_output,
        "timestamp": ts,
    }
    chat_collection.insert_one(doc)
    return doc


def fetch_history(session_id: str, limit: int = 50) -> List[tuple[str, str]]:
    cursor = (
        chat_collection.find({"session_id": session_id}, {"_id": 0, "user_input": 1, "ai_output": 1})
        .sort("timestamp", ASCENDING)
        .limit(limit)
    )
    rows: List[tuple[str, str]] = []
    for doc in cursor:
        rows.append((doc.get("user_input", ""), doc.get("ai_output", "")))
    return rows


def update_session_timestamps(session_id: str, timestamp: str) -> None:
    session_collection.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "session_id": session_id,
                "updated_at": timestamp,
            },
            "$setOnInsert": {"created_at": timestamp},
        },
        upsert=True,
    )


def rename_session(session_id: str, new_title: str, timestamp: str) -> None:
    session_collection.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "session_id": session_id,
                "title": new_title,
                "updated_at": timestamp,
            },
            "$setOnInsert": {"created_at": timestamp},
        },
        upsert=True,
    )


def delete_session(session_id: str) -> None:
    session_collection.delete_one({"session_id": session_id})
    chat_collection.delete_many({"session_id": session_id})


def _clean_numeric(doc: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in list(doc.items()):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            doc[key] = None
    return doc


def list_sessions() -> List[Dict[str, Any]]:
    sessions = {doc["session_id"]: doc for doc in session_collection.find({}, {"_id": 0}) if "session_id" in doc}

    pipeline = [
        {
            "$group": {
                "_id": "$session_id",
                "last_time": {"$max": "$timestamp"},
            }
        }
    ]
    for item in chat_collection.aggregate(pipeline):
        session_id = item["_id"]
        entry = sessions.setdefault(session_id, {"session_id": session_id})
        entry["last_time"] = item.get("last_time")

    ordered = sorted(
        sessions.values(),
        key=lambda doc: doc.get("last_time") or "",
        reverse=True,
    )
    return [_clean_numeric(doc) for doc in ordered]


def latest_message(session_id: str) -> Optional[Dict[str, Any]]:
    doc = chat_collection.find_one({"session_id": session_id}, sort=[("timestamp", DESCENDING)])
    if not doc:
        return None
    return _clean_numeric({key: doc.get(key) for key in ("user_input", "ai_output", "timestamp")})


def fetch_session_messages(session_id: str) -> List[Dict[str, Any]]:
    cursor = chat_collection.find({"session_id": session_id}, {"_id": 0}).sort("timestamp", ASCENDING)
    return [_clean_numeric(doc) for doc in cursor]
