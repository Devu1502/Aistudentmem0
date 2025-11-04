from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from openai import OpenAI

from config.settings import settings
from db.sqlite import get_connection
from memory import LocalMemory
from repositories import chat_repository, session_repository
from services.dependencies import get_memory_store
from utils.ids import generate_session_id


router = APIRouter()
openai_client = OpenAI()


@router.get("/sidebar_sessions")
def sidebar_sessions():
    with get_connection() as conn:
        chat_repository.ensure_table(conn)
        session_repository.ensure_table(conn)
        rows = session_repository.list_sessions(conn)
        sessions = []
        for row in rows:
            last_msg = session_repository.latest_message(conn, row["session_id"])
            preview = ""
            if last_msg:
                preview = last_msg["user_input"] or last_msg["ai_output"] or ""
            sessions.append(
                {
                    "session_id": row["session_id"],
                    "title": row["title"],
                    "last_message_time": row["last_time"],
                    "preview": preview,
                }
            )
        return {"sessions": sessions}


@router.delete("/delete_session")
def delete_session(session_id: str):
    with get_connection() as conn:
        chat_repository.ensure_table(conn)
        session_repository.ensure_table(conn)
        session_repository.delete_session(conn, session_id)
    return {"message": f"Session {session_id} deleted."}


@router.post("/rename_session")
def rename_session(session_id: str, new_name: str = Query(..., min_length=1)):
    timestamp = datetime.utcnow().isoformat()
    with get_connection() as conn:
        session_repository.ensure_table(conn)
        session_repository.rename_session(conn, session_id, new_name.strip(), timestamp)
    return {"message": f"Session {session_id} renamed."}


@router.get("/session_messages")
def session_messages(session_id: str):
    with get_connection() as conn:
        chat_repository.ensure_table(conn)
        rows = session_repository.fetch_session_messages(conn, session_id)
        messages = []
        for row in rows:
            if row["user_input"]:
                messages.append({"role": "teacher", "content": row["user_input"], "timestamp": row["timestamp"]})
            if row["ai_output"]:
                messages.append({"role": "assistant", "content": row["ai_output"], "timestamp": row["timestamp"]})
        return {"messages": messages}


@router.post("/session")
def new_session(topic: str = "general"):
    session_id = generate_session_id()
    timestamp = datetime.utcnow().isoformat()
    with get_connection() as conn:
        session_repository.ensure_table(conn)
        session_repository.rename_session(conn, session_id, topic, timestamp)
    return {"session_id": session_id, "message": f"New session started for topic '{topic}'."}


@router.post("/topic")
def set_topic(
    new_topic: str = Query(..., description="New topic to store"),
    user_id: str = "sree",
    session_id: Optional[str] = None,
    memory_store: LocalMemory = Depends(get_memory_store),
):
    topic_text = new_topic.strip()
    session_ref = session_id or generate_session_id()
    memory_store.add(
        f"Topic switched to {topic_text}",
        user_id=user_id,
        agent_id=topic_text,
        run_id=session_ref,
        metadata={"type": "system"},
    )
    with get_connection() as conn:
        session_repository.ensure_table(conn)
        session_repository.rename_session(conn, session_ref, topic_text, datetime.utcnow().isoformat())
    return {"message": f"Topic set to '{topic_text}'.", "session_id": session_ref}


@router.get("/summary")
def summarize_session(
    session_id: str = Query(..., description="Session to summarize"),
    memory_store: LocalMemory = Depends(get_memory_store),
):
    with get_connection() as conn:
        chat_repository.ensure_table(conn)
        rows = session_repository.fetch_session_messages(conn, session_id)

    if not rows:
        return {"session_id": session_id, "summary": "No conversation found for this session."}

    joined_transcript = "\n".join(
        f"Teacher: {row['user_input']}\nStudent: {row['ai_output']}" for row in rows if row["user_input"] or row["ai_output"]
    )

    prompt = (
        "Provide a concise summary (max 4 sentences) of the following teacher/student exchange. "
        "Focus on what the teacher taught and how the student responded.\n\n"
        f"{joined_transcript}"
    )
    response = openai_client.responses.create(
        model=settings.models.summary,
        input=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )
    summary_text = (response.output_text or "").strip()
    if not summary_text:
        summary_text = "Summary unavailable."

    memory_store.add(
        summary_text,
        user_id="sree",
        agent_id="general",
        run_id=session_id,
        metadata={"type": "session_summary"},
    )

    return {"session_id": session_id, "summary": summary_text}
