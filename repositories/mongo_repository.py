from __future__ import annotations

import os
from datetime import datetime
import math
from typing import Any, Dict, List, Optional
from pymongo import ASCENDING, DESCENDING, MongoClient
from bson import ObjectId

MONGO_URI = os.getenv("MONGODB_URI")
if not MONGO_URI:
    raise RuntimeError("MONGODB_URI environment variable is required for MongoDB repository.")

client = MongoClient(MONGO_URI)
db = client["AIBuddy"]
chat_collection = db["chat_messages"]
session_collection = db["sessions"]
summary_collection = db["session_summaries"]


def _normalize_user_id(user_id: str | ObjectId | None) -> Optional[ObjectId]:
    if not user_id:
        return None
    if isinstance(user_id, ObjectId):
        return user_id
    try:
        return ObjectId(user_id)
    except Exception:
        return None


def _ensure_indexes() -> None:
    chat_collection.create_index([("session_id", ASCENDING), ("timestamp", DESCENDING)])
    chat_collection.create_index([("session_id", ASCENDING), ("user_id", ASCENDING)])
    session_collection.create_index([("session_id", ASCENDING)], unique=True)
    session_collection.create_index([("user_id", ASCENDING), ("session_id", ASCENDING)])
    summary_collection.create_index([("created_at", DESCENDING)])
    summary_collection.create_index([("session_id", ASCENDING), ("created_at", DESCENDING)])
    summary_collection.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])


_ensure_indexes()


def insert_message(
    session_id: str,
    user_input: str,
    ai_output: str,
    timestamp: Optional[str] = None,
    user_id: Optional[str | ObjectId] = None,
) -> Dict[str, Any]:
    ts = timestamp or datetime.utcnow().isoformat()
    doc = {
        "session_id": session_id,
        "user_input": user_input,
        "ai_output": ai_output,
        "timestamp": ts,
    }
    normalized = _normalize_user_id(user_id)
    if normalized:
        doc["user_id"] = normalized
    chat_collection.insert_one(doc)
    return doc


def fetch_history(session_id: str, user_id: Optional[str | ObjectId], limit: int = 50) -> List[tuple[str, str]]:
    filters: Dict[str, Any] = {"session_id": session_id}
    normalized = _normalize_user_id(user_id)
    if normalized:
        filters["user_id"] = normalized
    cursor = (
        chat_collection.find(filters, {"_id": 0, "user_input": 1, "ai_output": 1})
        .sort("timestamp", ASCENDING)
        .limit(limit)
    )
    rows: List[tuple[str, str]] = []
    for doc in cursor:
        rows.append((doc.get("user_input", ""), doc.get("ai_output", "")))
    return rows


def update_session_timestamps(session_id: str, timestamp: str, user_id: Optional[str | ObjectId]) -> None:
    normalized = _normalize_user_id(user_id)
    session_collection.update_one(
        {"session_id": session_id, "user_id": normalized},
        {
            "$set": {
                "session_id": session_id,
                "updated_at": timestamp,
                "user_id": normalized,
            },
            "$setOnInsert": {"created_at": timestamp},
        },
        upsert=True,
    )


def rename_session(session_id: str, new_title: str, timestamp: str, user_id: Optional[str | ObjectId]) -> None:
    normalized = _normalize_user_id(user_id)
    session_collection.update_one(
        {"session_id": session_id, "user_id": normalized},
        {
            "$set": {
                "session_id": session_id,
                "title": new_title,
                "user_id": normalized,
                "updated_at": timestamp,
            },
            "$setOnInsert": {"created_at": timestamp},
        },
        upsert=True,
    )


def delete_session(session_id: str, user_id: Optional[str | ObjectId]) -> None:
    normalized = _normalize_user_id(user_id)
    filter_query = {"session_id": session_id}
    if normalized:
        filter_query["user_id"] = normalized
    session_collection.delete_one(filter_query)
    chat_collection.delete_many(filter_query)
    summary_collection.delete_many(filter_query)


def _clean_numeric(doc: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in list(doc.items()):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            doc[key] = None
    return doc


def list_sessions(user_id: Optional[str | ObjectId]) -> List[Dict[str, Any]]:
    normalized = _normalize_user_id(user_id)
    query = {"user_id": normalized} if normalized else {}
    sessions = {doc["session_id"]: doc for doc in session_collection.find(query, {"_id": 0}) if "session_id" in doc}

    pipeline = [
        {
            "$group": {
                "_id": "$session_id",
                "last_time": {"$max": "$timestamp"},
            }
        }
    ]
    pipeline_match = {"$match": query} if query else None
    aggregate_pipeline = []
    if pipeline_match:
        aggregate_pipeline.append(pipeline_match)
    aggregate_pipeline.extend(pipeline)
    for item in chat_collection.aggregate(aggregate_pipeline):
        session_id = item["_id"]
        entry = sessions.setdefault(session_id, {"session_id": session_id})
        entry["last_time"] = item.get("last_time")

    ordered = sorted(
        sessions.values(),
        key=lambda doc: doc.get("last_time") or "",
        reverse=True,
    )
    return [_clean_numeric(doc) for doc in ordered]


def latest_message(session_id: str, user_id: Optional[str | ObjectId]) -> Optional[Dict[str, Any]]:
    filters = {"session_id": session_id}
    normalized = _normalize_user_id(user_id)
    if normalized:
        filters["user_id"] = normalized
    doc = chat_collection.find_one(filters, sort=[("timestamp", DESCENDING)])
    if not doc:
        return None
    return _clean_numeric({key: doc.get(key) for key in ("user_input", "ai_output", "timestamp")})


def fetch_session_messages(session_id: str, user_id: Optional[str | ObjectId]) -> List[Dict[str, Any]]:
    filters = {"session_id": session_id}
    normalized = _normalize_user_id(user_id)
    if normalized:
        filters["user_id"] = normalized
    cursor = chat_collection.find(filters, {"_id": 0}).sort("timestamp", ASCENDING)
    return [_clean_numeric(doc) for doc in cursor]


def insert_session_summary(
    session_id: str,
    teacher_summary: str,
    student_summary: str,
    user_id: Optional[str | ObjectId],
    created_at: Optional[datetime] = None,
) -> None:
    normalized = _normalize_user_id(user_id)
    summary_doc = {
        "session_id": session_id,
        "teacher_summary": teacher_summary,
        "student_summary": student_summary,
        "user_id": normalized,
        "created_at": created_at or datetime.utcnow(),
    }
    summary_collection.insert_one(summary_doc)


def fetch_recent_session_summaries(limit: int = 2, user_id: Optional[str | ObjectId] = None) -> List[Dict[str, Any]]:
    filters = {}
    normalized = _normalize_user_id(user_id)
    if normalized:
        filters["user_id"] = normalized
    docs = summary_collection.find(filters, {"_id": 0}).sort("created_at", DESCENDING).limit(limit)
    return [_clean_numeric(doc) for doc in docs]
