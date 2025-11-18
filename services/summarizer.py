# Async helper to create OpenAI-driven session summaries.
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Tuple

from openai import OpenAI

from config.settings import settings
from repositories.mongo_repository import insert_session_summary

# Reuse one OpenAI client for all summarization calls.
_client = OpenAI()


# Kick off a background summary generation and persistence task.
async def summarize_session(session_id: str, teacher_text: str, student_text: str, user_id: str) -> None:
    """Generate and store a compact summary for the session."""

    # Run the actual network call on a thread to avoid blocking FastAPI.
    def _run() -> Tuple[str, str]:
        if not teacher_text and not student_text:
            return "", ""

        prompt = (
            f"Summarize session {session_id} in two short sections.\n"
            f"1. Teacher Summary – capture what was taught.\n"
            f"2. Student Summary – capture questions or understanding.\n\n"
            f"Teacher dialog:\n{teacher_text or 'N/A'}\n\n"
            f"Student dialog:\n{student_text or 'N/A'}"
        )
        response = _client.responses.create(
            model=settings.models.summary,
            input=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
        summary_text = (response.output_text or "").strip()
        teacher_summary = ""
        student_summary = ""
        if summary_text:
            parts = summary_text.split("Student Summary:")
            teacher_summary = parts[0].replace("Teacher Summary:", "").strip()
            if len(parts) > 1:
                student_summary = parts[1].strip()
        return teacher_summary, student_summary

    teacher_summary, student_summary = await asyncio.to_thread(_run)
    if not (teacher_summary or student_summary):
        return
    # Store the results so dashboards can surface them later.
    insert_session_summary(
        session_id=session_id,
        teacher_summary=teacher_summary,
        student_summary=student_summary,
        user_id=user_id,
        created_at=datetime.utcnow(),
    )
