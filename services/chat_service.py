# Service responsible for orchestrating LLM calls for each chat turn.
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, Optional

from agents import Runner  # type: ignore

from config.prompts import DEFAULT_AGENT_INSTRUCTIONS
from core.agent import chat_agent
from doc_store import DocumentStore
from intent_utils import handle_system_action, sanitize_reply
from memory import LocalMemory
from repositories import chat_repository, session_repository
from services.context_builder import ContextBuilder, ContextResult
from services.summarizer import summarize_session
from services.token_utils import count_tokens
from teach_mode import is_teach_mode_on
from utils.ids import generate_session_id


class ChatService:
    # Keep references to storage backends and helpers needed per request.
    def __init__(self, memory_store: LocalMemory, document_store: DocumentStore) -> None:
        self.memory_store = memory_store
        self.document_store = document_store
        self.context_builder = ContextBuilder(memory_store, document_store)

    # Main entry point for handling a user prompt and returning an answer.
    async def handle_chat(self, prompt: str, session_id: Optional[str], user_id: str) -> Dict[str, str | int | bool | None]:
        active_session = session_id or generate_session_id()
        teach_on = is_teach_mode_on()

        context = self.context_builder.build(prompt, active_session, teach_on, user_id)

        # Teach mode skips historical context and just prints debug info.
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
        # Combine all context elements before building final prompt
        combined_context = ""
        # if context.document_hits:
        #     combined_context += "[Uploaded Document Context]\n" + "\n".join(context.document_hits) + "\n\n"
        if context.memory_hits:
            combined_context += "[Related Memories]\n" + "\n".join(context.memory_hits) + "\n\n"
        if context.chat_context:
            combined_context += f"[Conversation History]\n{context.chat_context}\n\n"


        # Override chat_context for prompt composition
        context.chat_context = combined_context



        user_prompt = self._compose_prompt(
            active_session,
            teach_on,
            context.session_summaries,
            context.chat_context,
            prompt,
        )


        # user_prompt += "\n\nIf any uploaded document context mentions the current topic, summarize what is visible in that document and include a final 'Sources:' section following your formatting rules."
        preview_context = "" if teach_on else context.chat_context
        print("Calling OpenAI Agent (async)...")
        # print(f"LLM context preview (first 1000 chars):\n{preview_context[:1000]}")


        # 🔍 Print full composed prompt (to verify document + memory context injection)
        print("\n========== FULL PROMPT SENT TO LLM ==========")
        print(user_prompt)
        print("========== END FULL PROMPT ==========\n")

        # Show a quick human-readable summary of what we sent downstream.
        self._print_context_outline(context)

        # Ask the LangGraph agent to answer the teacher prompt.
        result = await Runner.run(chat_agent, user_prompt)
        raw_reply = getattr(result, "final_output", "") or ""
        print(f"Raw LLM reply: {raw_reply!r}")

        # Clean up the reply, handle teach mode, and run system actions if needed.
        reply_text = self._prepare_reply(raw_reply, teach_on)
        silent = teach_on
        reply_text, action_data = sanitize_reply(reply_text)

        if action_data:
            sys_reply, _ = handle_system_action(action_data, active_session, self.memory_store, user_id)
            if sys_reply:
                reply_text = sys_reply
                silent = False

        reply_text, sources_block = self._split_sources_block(reply_text)
        if sources_block:
            print("Captured sources block from reply:")
            print(sources_block)

        # Store a short-turn summary inside the memory store.
        conversation_summary = f"Teacher: {prompt}\nStudent: {reply_text}"
        self.memory_store.add(
q            user_id=user_id,
            agent_id="general",
            run_id=active_session,
            metadata={"type": "short_term"},
        )
        print(f"Storing short-term memory snippet:\n{conversation_summary[:300]}")

        timestamp = datetime.utcnow().isoformat()
        user_entry = prompt if not self._is_context_block(prompt) else ""
        reply_entry = reply_text if not self._is_context_block(reply_text) else ""
        # Persist the chat turn and keep the session heartbeat fresh.
        if user_entry or reply_entry:
            chat_repository.insert_message(None, active_session, user_entry, reply_entry, timestamp, user_id)
        session_repository.update_session_timestamps(None, active_session, timestamp, user_id)

        # Periodically trigger a background summary for lengthy sessions.
        self._maybe_queue_summary(context, active_session, user_id)

        print("Chat record inserted successfully.")

        return {
            "response": reply_text,
            "context_count": len(context.history_rows),
            "session_id": active_session,
            "silent": silent,
        }

    @staticmethod
    # Build the system prompt that wraps context, summaries, and instructions.
    def _compose_prompt(
        session_id: str,
        teach_on: bool,
        session_summaries: str,
        chat_context: str,
        prompt: str,
    ) -> str:
        context_section = chat_context if not teach_on else ""
        summaries_section = f"[Session Summaries]\n{session_summaries.strip()}\n\n" if session_summaries else ""
        return (
            f"[Session: {session_id}] [TeachMode: {'ON' if teach_on else 'OFF'}]\n"
            f"[Time: {datetime.utcnow().isoformat()}]\n"
            f"{context_section}\n"
            f"{summaries_section}"
            f"\n---\nIMPORTANT:\n"
            f" • Treat [Uploaded Document Context] and [Related Memories] as previously taught material whenever relevant.\n"
            f" • When the teacher paraphrases earlier topics, infer continuity and answer using prior knowledge.\n"
            f" • Student messages are conversational reflections only; rely on Teacher and Document content for facts.\n"
            f" • Summaries of prior sessions are authoritative for continuing the current dialogue.\n"
            f"{DEFAULT_AGENT_INSTRUCTIONS.strip()}\n\n"
            f"Teacher: {prompt}\nStudent:"
        )


    @staticmethod
    # Skip LLM output when teach mode is enabled; otherwise tidy the reply.
    def _prepare_reply(raw_reply: str, teach_on: bool) -> str:
        if teach_on:
            return ""
        reply = raw_reply.strip()
        return reply if reply else "Agent returned no output."

    @staticmethod
    # Separate any trailing "Sources:" block from the main answer text.
    def _split_sources_block(reply: str) -> tuple[str, str]:
        if not reply:
            return "", ""
        marker = "Sources:"
        idx = reply.find(marker)
        if idx == -1:
            return reply.strip(), ""
        main_response = reply[:idx].rstrip()
        sources_section = reply[idx:].strip()
        return main_response, sources_section

    def _maybe_queue_summary(self, context: ContextResult, session_id: str, user_id: str) -> None:
        turn_count = len(context.history_rows)
        token_count = count_tokens(context.chat_context)
        if turn_count == 0:
            return
        if token_count <= 2000 and turn_count % 6 != 0:
            return

        teacher_lines = [row[0] for row in context.history_rows if row and row[0]]
        student_lines = [row[1] for row in context.history_rows if row and row[1]]
        teacher_text = "\n".join(teacher_lines)
        student_text = "\n".join(student_lines)
        if not teacher_text and not student_text:
            return

        asyncio.create_task(summarize_session(session_id, teacher_text, student_text, user_id))

    @staticmethod
    # Ignore context scaffolding when deciding whether to log a message.
    def _is_context_block(text: str) -> bool:
        if not text:
            return False
        trimmed = text.strip()
        disallowed_prefixes = (
            "[Uploaded Document Context]",
            "[Related Memories]",
            "[Session Summaries]",
            "========== FULL PROMPT",
            "========== CONTEXT OUTLINE",
        )
        return any(trimmed.startswith(prefix) for prefix in disallowed_prefixes)

    def _print_context_outline(self, context: ContextResult) -> None:
        # Print a quick digest of each context slice for debugging.
        def preview_section(title: str, text: str, limit: int = 100) -> None:
            if not text:
                print(f"⚪ {title}: None")
                return
            words = text.split()
            preview = " ".join(words[:limit])
            if len(words) > limit:
                preview += " ..."
            print(f"🟢 {title} ({len(words)} words):\n{preview}\n")

        print("\n========== CONTEXT OUTLINE ==========")
        preview_section("Uploaded Document Context", "\n".join(context.document_hits))
        preview_section("Related Memories", "\n".join(context.memory_hits))
        preview_section("Session Summaries", context.session_summaries or "")
        preview_section("Conversation History", context.chat_context)
        print("========== END OUTLINE ==========\n")
        print(
            "Token counts — "
            f"Docs:{count_tokens(' '.join(context.document_hits))} | "
            f"Mem:{count_tokens(' '.join(context.memory_hits))} | "
            f"Summ:{count_tokens(context.session_summaries or '')} | "
            f"Chat:{count_tokens(context.chat_context)}"
        )
