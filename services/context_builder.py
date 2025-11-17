from __future__ import annotations

from dataclasses import dataclass
from typing import List

from config.settings import settings
from config.hyperparameters import hyperparams
from doc_store import DocumentStore
from memory import LocalMemory
from repositories import chat_repository
from repositories.mongo_repository import fetch_recent_session_summaries


@dataclass
class ContextResult:
    chat_context: str
    history_rows: List[tuple[str, str]]
    memory_hits: List[str]
    document_hits: List[str]
    session_summaries: str


class ContextBuilder:
    def __init__(self, memory_store: LocalMemory, document_store: DocumentStore) -> None:
        self.memory_store = memory_store
        self.document_store = document_store

    def build(
        self,
        prompt: str,
        session_id: str,
        teach_mode: bool,
        user_id: str,
    ) -> ContextResult:
        if teach_mode:
            return ContextResult(chat_context="", history_rows=[], memory_hits=[], document_hits=[], session_summaries="")

        history_rows = chat_repository.fetch_history(None, session_id, user_id)
        history_rows_limited = history_rows[-hyperparams.max_history_turns :]
        history_text = "\n".join(
            [f"Teacher: {row[0]}\nStudent: {row[1]}" for row in history_rows_limited if row]
        )

        memory_hits = self._memory_hits(prompt, session_id, user_id)
        doc_hits = self._document_hits(prompt, user_id)
        summary_text = self._session_summaries(user_id=user_id)

        unique_docs = list(dict.fromkeys(doc_hits))[: hyperparams.document_limit]
        memory_hits = memory_hits[: hyperparams.memory_limit]
        doc_section = ""
        mem_section = ""
        if unique_docs:
            doc_section = "[Uploaded Document Context]\n" + "\n\n".join(unique_docs)
        if memory_hits:
            mem_section = "[Related Memories]\n" + "\n".join(memory_hits)
        chat_context = "\n\n".join([s for s in [doc_section, mem_section, history_text] if s])
        return ContextResult(
            chat_context=chat_context,
            history_rows=history_rows,
            memory_hits=memory_hits,
            document_hits=doc_hits,
            session_summaries=summary_text,
        )

    def _memory_hits(self, prompt: str, session_id: str, user_id: str) -> List[str]:
        results = self.memory_store.search(
            query=prompt,
            user_id=user_id,
            agent_id="general",
            run_id=session_id,
            limit=settings.vectors.chat_search_limit,
        )
        combined = results.get("results", []) if isinstance(results, dict) else []
        if len(combined) < settings.vectors.chat_search_limit:
            global_hits = self.memory_store.search(
                query=prompt,
                user_id=user_id,
                agent_id="general",
                limit=settings.vectors.chat_search_limit,
            ).get("results", [])
            seen = {item.get("id") for item in combined}
            for item in global_hits:
                if item.get("id") not in seen:
                    combined.append(item)
                    seen.add(item.get("id"))
                    if len(combined) >= settings.vectors.chat_search_limit:
                        break

        hits = []
        for item in combined:
            text = item.get("memory")
            if text:
                hits.append(text)
        return hits

    def _document_hits(self, prompt: str, user_id: str) -> List[str]:
        filters = {"user_id": user_id}
        results = self.document_store.search(prompt, limit=hyperparams.document_limit, filters=filters)
        doc_hits = results.get("results", []) if isinstance(results, dict) else []
        snippets = []
        for item in doc_hits[: hyperparams.document_limit]:
            meta = item.get("metadata", {})
            title = meta.get("title") or meta.get("filename") or "Document"
            snippet = item.get("memory") or ""
            snippets.append(f"{title}:\n{snippet}")
        return snippets

    @staticmethod
    def _session_summaries(limit: int = hyperparams.summary_limit, user_id: str | None = None) -> str:
        docs = fetch_recent_session_summaries(limit=limit, user_id=user_id)
        if not docs:
            return ""
        blocks: List[str] = []
        for doc in docs:
            sid = doc.get("session_id", "unknown")
            teacher_summary = doc.get("teacher_summary", "").strip()
            student_summary = doc.get("student_summary", "").strip()
            parts = []
            if teacher_summary:
                parts.append(f"[Teacher Summary - {sid}]\n{teacher_summary}")
            if student_summary:
                parts.append(f"[Student Summary - {sid}]\n{student_summary}")
            if parts:
                blocks.append("\n".join(parts))
        return "\n\n".join(blocks)
