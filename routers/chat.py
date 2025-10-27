from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from intent_utils import detect_dev_command
from memory import LocalMemory
from services.chat_service import ChatService
from services.dependencies import get_chat_service, get_memory_store


router = APIRouter()


@router.post("/chat")
async def chat_endpoint(
    prompt: str,
    session_id: Optional[str] = Query(None),
    chat_service: ChatService = Depends(get_chat_service),
    memory_store: LocalMemory = Depends(get_memory_store),
):
    dev_cmd = detect_dev_command(prompt)
    if dev_cmd:
        if dev_cmd["cmd"] == "search_topic":
            query = dev_cmd.get("arg", "")
            if not query:
                return {"response": "Provide a search query."}
            results = memory_store.search(query=query, user_id="sree")
            hits = results.get("results", []) if isinstance(results, dict) else []
            formatted = []
            for idx, item in enumerate(hits[:5]):
                formatted.append(
                    f"{idx + 1}. {item.get('memory', '')}\n   score: {item.get('score', '?')}"
                )
            return {
                "response":
                f"🔍 Found {len(hits)} results for '{query}'.\n\n" + "\n\n".join(formatted),
                "context_count": 0,
                "session_id": session_id,
            }
        if dev_cmd["cmd"] == "reset":
            memory_store.reset()
            return {"response": "🧹 Memory store reset successfully.", "context_count": 0, "session_id": session_id}

    return await chat_service.handle_chat(prompt, session_id)
