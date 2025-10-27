from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from config.settings import settings
from doc_store import DocumentStore
from memory import LocalMemory
from repositories import chat_repository


@dataclass
class ContextResult:
    chat_context: str
    history_rows: List[tuple[str, str]]
    memory_hits: List[str]
    document_hits: List[str]


class ContextBuilder:
    def __init__(self, memory_store: LocalMemory, document_store: DocumentStore) -> None:
        self.memory_store = memory_store
        self.document_store = document_store

    def build(
        self,
        conn,
        prompt: str,
        session_id: str,
        teach_mode: bool,
    ) -> ContextResult:
        if teach_mode:
            return ContextResult(chat_context="", history_rows=[], memory_hits=[], document_hits=[])

        history_rows = chat_repository.fetch_history(conn, session_id)
        history_text = "\n".join(
            [f"Teacher: {row[0]}\nStudent: {row[1]}" for row in history_rows if row]
        )

        memory_hits = self._memory_hits(prompt, session_id)
        doc_hits = self._document_hits(prompt)

        sections = [history_text] if history_text else []
        if memory_hits:
            sections.append("[Relevant Past Knowledge]\n" + "\n".join(memory_hits))
        if doc_hits:
            sections.append("[Uploaded Document Context]\n" + "\n\n".join(doc_hits))

        chat_context = "\n\n".join([s for s in sections if s])
        return ContextResult(chat_context=chat_context, history_rows=history_rows, memory_hits=memory_hits, document_hits=doc_hits)

    def _memory_hits(self, prompt: str, session_id: str) -> List[str]:
        results = self.memory_store.search(
            query=prompt,
            user_id="sree",
            agent_id="general",
            run_id=session_id,
            limit=settings.vectors.chat_search_limit,
        )
        combined = results.get("results", []) if isinstance(results, dict) else []
        if len(combined) < settings.vectors.chat_search_limit:
            global_hits = self.memory_store.search(
                query=prompt,
                user_id="sree",
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

    def _document_hits(self, prompt: str) -> List[str]:
        results = self.document_store.search(prompt, limit=settings.vectors.document_search_limit)
        doc_hits = results.get("results", []) if isinstance(results, dict) else []
        snippets = []
        for item in doc_hits[: settings.vectors.document_search_limit]:
            meta = item.get("metadata", {})
            title = meta.get("title") or meta.get("filename") or "Document"
            snippet = item.get("memory") or ""
            snippets.append(f"{title}:\n{snippet}")
        return snippets
