from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from agents import Runner  # type: ignore

from core.agent import chat_agent
from db.sqlite import get_connection
from doc_store import DocumentStore
from intent_utils import handle_system_action, sanitize_reply
from memory import LocalMemory
from repositories import chat_repository, session_repository
from services.context_builder import ContextBuilder
from teach_mode import is_teach_mode_on
from utils.ids import generate_session_id


class ChatService:
    def __init__(self, memory_store: LocalMemory, document_store: DocumentStore) -> None:
        self.memory_store = memory_store
        self.document_store = document_store
        self.context_builder = ContextBuilder(memory_store, document_store)

    async def handle_chat(self, prompt: str, session_id: Optional[str]) -> Dict[str, str | int | None]:
        active_session = session_id or generate_session_id()
        teach_on = is_teach_mode_on()

        with get_connection() as conn:
            chat_repository.ensure_table(conn)
            session_repository.ensure_table(conn)
            context = self.context_builder.build(conn, prompt, active_session, teach_on)

        if teach_on:
            print("Teach Mode active - skipping chat history aggregation.")
        else:
            print(f"Loaded {len(context.history_rows)} previous messages for context.")
            if context.memory_hits:
                print(f"Retrieved {len(context.memory_hits)} related memories from vector store.")
            else:
                print("Retrieved 0 related memories from vector store.")
            if context.document_hits:
                print(f"Document hits: {len(context.document_hits)}")
                print("Appending document context:")
                for preview in context.document_hits[:3]:
                    trimmed = preview.replace("\n", " ")
                    snippet = trimmed[:160]
                    if len(trimmed) > 160:
                        snippet += '...'
                    print(f"    - {snippet}")
            else:
                print("Document hits: none")

        user_prompt = self._compose_prompt(active_session, teach_on, context.chat_context, prompt)
        preview_context = "" if teach_on else context.chat_context
        print("Calling OpenAI Agent (async)...")
        print(f"LLM context preview (first 1000 chars):\n{preview_context[:1000]}")

        result = await Runner.run(chat_agent, user_prompt)
        raw_reply = getattr(result, "final_output", "") or ""
        print(f"Raw LLM reply: {raw_reply!r}")

        reply_text = self._prepare_reply(raw_reply, teach_on)
        reply_text, action_data = sanitize_reply(reply_text)

        if action_data:
            sys_reply, _ = handle_system_action(action_data, active_session, self.memory_store)
            if sys_reply:
                return {
                    "response": sys_reply,
                    "context_count": len(context.history_rows),
                    "session_id": active_session,
                }

        conversation_summary = f"Teacher: {prompt}\nStudent: {reply_text}"
        self.memory_store.add(
            conversation_summary,
            user_id="sree",
            agent_id="general",
            run_id=active_session,
            metadata={"type": "short_term"},
        )
        print(f"Storing short-term memory snippet:\n{conversation_summary[:300]}")

        timestamp = datetime.utcnow().isoformat()
        with get_connection() as conn:
            chat_repository.ensure_table(conn)
            session_repository.ensure_table(conn)
            chat_repository.insert_message(conn, active_session, prompt, reply_text, timestamp)
            session_repository.update_session_timestamps(conn, active_session, timestamp)

        print("Chat record inserted successfully.")

        return {
            "response": reply_text,
            "context_count": len(context.history_rows),
            "session_id": active_session,
        }

    @staticmethod
    def _compose_prompt(session_id: str, teach_on: bool, chat_context: str, prompt: str) -> str:
        context_section = chat_context if not teach_on else ""
        return (
            f"[Session: {session_id}] [TeachMode: {'ON' if teach_on else 'OFF'}]\n"
            f"[Time: {datetime.utcnow().isoformat()}]\n"
            f"Context:\n{context_section}\n\nTeacher: {prompt}\nStudent:"
        )

    @staticmethod
    def _prepare_reply(raw_reply: str, teach_on: bool) -> str:
        if teach_on:
            return " "
        reply = raw_reply.strip()
        return reply if reply else "Agent returned no output."
