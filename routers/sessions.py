from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from openai import OpenAI

from config.settings import settings
from memory import LocalMemory
from repositories import session_repository
from services.dependencies import get_memory_store
from utils.ids import generate_session_id
from services.auth_service import protect


router = APIRouter()
openai_client = OpenAI()


@router.get("/sidebar_sessions")
def sidebar_sessions(current_user: dict = Depends(protect)):
    user_id = current_user["id"]
    rows = session_repository.list_sessions(None, user_id)
    sessions = []
    for row in rows:
        session_id = row.get("session_id")
        last_msg = session_repository.latest_message(None, session_id, user_id)
        preview = ""
        if last_msg:
            preview = last_msg.get("user_input") or last_msg.get("ai_output") or ""
        sessions.append(
            {
                "session_id": session_id,
                "title": row.get("title", ""),
                "last_message_time": row.get("last_time"),
                "preview": preview,
            }
        )
    return {"sessions": sessions}


@router.delete("/delete_session")
def delete_session(session_id: str, current_user: dict = Depends(protect)):
    session_repository.delete_session(None, session_id, current_user["id"])
    return {"message": f"Session {session_id} deleted."}


@router.post("/rename_session")
def rename_session(
    session_id: str,
    new_name: str = Query(..., min_length=1),
    current_user: dict = Depends(protect),
):
    timestamp = datetime.utcnow().isoformat()
    session_repository.rename_session(None, session_id, new_name.strip(), timestamp, current_user["id"])
    return {"message": f"Session {session_id} renamed."}


@router.get("/session_messages")
def session_messages(session_id: str, current_user: dict = Depends(protect)):
    rows = session_repository.fetch_session_messages(None, session_id, current_user["id"])
    messages = []
    for row in rows:
        user_input = row.get("user_input")
        ai_output = row.get("ai_output")
        timestamp = row.get("timestamp")
        if user_input:
            messages.append({"role": "teacher", "content": user_input, "timestamp": timestamp})
        if ai_output:
            messages.append({"role": "assistant", "content": ai_output, "timestamp": timestamp})
    return {"messages": messages}


@router.post("/session")
def new_session(topic: str = "general", current_user: dict = Depends(protect)):
    session_id = generate_session_id()
    timestamp = datetime.utcnow().isoformat()
    session_repository.rename_session(None, session_id, topic, timestamp, current_user["id"])
    return {"session_id": session_id, "message": f"New session started for topic '{topic}'."}


@router.post("/topic")
def set_topic(
    new_topic: str = Query(..., description="New topic to store"),
    session_id: Optional[str] = None,
    memory_store: LocalMemory = Depends(get_memory_store),
    current_user: dict = Depends(protect),
):
    topic_text = new_topic.strip()
    session_ref = session_id or generate_session_id()
    memory_store.add(
        f"Topic switched to {topic_text}",
        user_id=current_user["id"],
        agent_id=topic_text,
        run_id=session_ref,
        metadata={"type": "system"},
    )
    session_repository.rename_session(
        None, session_ref, topic_text, datetime.utcnow().isoformat(), current_user["id"]
    )
    return {"message": f"Topic set to '{topic_text}'.", "session_id": session_ref}


@router.get("/summary")
def summarize_session(
    session_id: str = Query(..., description="Session to summarize"),
    memory_store: LocalMemory = Depends(get_memory_store),
    current_user: dict = Depends(protect),
):
    rows = session_repository.fetch_session_messages(None, session_id, current_user["id"])

    if not rows:
        return {"session_id": session_id, "summary": "No conversation found for this session."}

    joined_transcript = "\n".join(
        f"Teacher: {row.get('user_input')}\nStudent: {row.get('ai_output')}"
        for row in rows
        if row.get("user_input") or row.get("ai_output")
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
        user_id=current_user["id"],
        agent_id="general",
        run_id=session_id,
        metadata={"type": "session_summary"},
    )

    return {"session_id": session_id, "summary": summary_text}
