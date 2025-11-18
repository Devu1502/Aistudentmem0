"""
Document storage and retrieval utilities backed by Qdrant.

This module keeps the logic for handling uploaded documents separate from the
core conversational memory so it can be swapped to a remote Qdrant instance
without touching the FastAPI routes.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from memory import OpenAIEmbedder

from config.settings import settings

# Log ingestion activity and vector store errors for debugging.
logger = logging.getLogger(__name__)


def _chunk_paragraphs(text: str, max_chars: int = 1200) -> List[str]:
    """
    Split text into reasonably sized chunks preserving paragraph boundaries.
    """
    if not text:
        return []

    paragraphs: List[str] = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [text.strip()]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current and current_len + para_len + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len + (2 if current_len else 0)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


class DocumentStore:
    """
    Lightweight wrapper around Qdrant for document embeddings.
    """

    def __init__(
        self,
        qdrant_client: Optional[QdrantClient] = None,
        embedder: Optional[OpenAIEmbedder] = None,
        collection_name: str = "mem0_documents",
        dimension: int = settings.vectors.embedding_dim,
        distance: Distance = Distance.COSINE,
    ) -> None:
        self.collection_name = collection_name
        self.dimension = dimension
        self._client = qdrant_client or QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            prefer_grpc=False,
        )
        self._embedder = embedder or OpenAIEmbedder(model=settings.models.embed)
        self._distance = distance
        self._ensure_collection()
        logger.info("DocumentStore ready (collection=%s)", self.collection_name)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _ensure_collection(self) -> None:
        try:
            info = self._client.get_collection(self.collection_name)
            current_dim = info.config.params.vectors.size
            if current_dim != self.dimension:
                logger.warning(
                    "DocumentStore: dimension mismatch (expected=%s, got=%s); recreating collection %s",
                    self.dimension,
                    current_dim,
                    self.collection_name,
                )
                try:
                    self._client.delete_collection(self.collection_name)
                except Exception as exc:
                    if self._is_forbidden_error(exc):
                        logger.warning("DocumentStore: cannot delete collection (forbidden): %s", exc)
                        return
                    raise
                self._create_collection()
        except Exception as exc:
            if self._is_forbidden_error(exc):
                logger.warning(
                    "DocumentStore: skipping ensure for %s; permission denied: %s",
                    self.collection_name,
                    exc,
                )
                return
            self._create_collection()

    def _create_collection(self) -> None:
        try:
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.dimension, distance=self._distance),
            )
        except Exception as exc:
            if self._is_forbidden_error(exc):
                logger.warning(
                    "DocumentStore: skipping create for %s; permission denied: %s",
                    self.collection_name,
                    exc,
                )
                return
            raise

    # Convert raw text chunks into Qdrant points with metadata.
    def _encode_chunks(
        self,
        doc_id: str,
        title: str,
        chunks: Sequence[str],
        metadata: Dict[str, Any],
    ) -> List[PointStruct]:
        points: List[PointStruct] = []
        for idx, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            vector = self._embedder.embed(chunk)
            payload = {
                "text": chunk,
                "doc_id": doc_id,
                "chunk_index": idx,
                "chunk_total": len(chunks),
                "title": title,
                **metadata,
            }
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector.tolist(),
                    payload=payload,
                )
            )
        return points

    # Turn simple equality filters into Qdrant filter objects.
    def _build_filter(self, filters: Optional[Dict[str, Any]]) -> Optional[Filter]:
        if not filters:
            return None

        conditions: List[FieldCondition] = []
        for key, value in filters.items():
            if isinstance(value, dict):
                eq_value = value.get("eq")
                if eq_value is not None:
                    conditions.append(FieldCondition(key=key, match=MatchValue(value=eq_value)))
            else:
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))

        return Filter(must=conditions) if conditions else None

    @staticmethod
    # Recognize permission errors that should not crash ingestion.
    def _is_forbidden_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "forbidden" in message or "403" in message

    @staticmethod
    # Without payload indexes we have to filter results manually.
    def _needs_manual_filter(exc: Exception) -> bool:
        message = str(exc).lower()
        return "index required" in message or "payload index" in message

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def add_document(
        self,
        title: str,
        text: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Embed the provided text and persist chunks to Qdrant.
        """
        if not text or not text.strip():
            raise ValueError("Cannot ingest empty document text.")

        doc_id = str(uuid.uuid4())
        base_metadata = {
            "title": title,
            "uploaded_at": datetime.utcnow().isoformat(),
        }
        if metadata:
            base_metadata.update(metadata)

        chunks = _chunk_paragraphs(text)
        points = self._encode_chunks(doc_id, title, chunks, base_metadata)
        if not points:
            raise ValueError("No content to store after chunking.")

        self._client.upsert(collection_name=self.collection_name, points=points, wait=True)
        logger.info("Stored document %s with %s chunks", title, len(points))
        return {"doc_id": doc_id, "chunks": len(points)}

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        if not query or not query.strip():
            return {"results": []}

        vector = self._embedder.embed(query)
        query_filter = self._build_filter(filters)
        hits = self._run_similarity_search(
            embedding=vector.tolist(),
            limit=limit,
            score_threshold=score_threshold,
            query_filter=query_filter,
            combined_filters=filters or {},
        )

        formatted = [
            {
                "id": point.id,
                "score": point.score,
                "memory": point.payload.get("text", ""),
                "metadata": {k: v for k, v in point.payload.items() if k not in {"text"}},
            }
            for point in hits
        ]
        return {"results": formatted}

    # Preferred query path that lets Qdrant handle filters.
    def _run_similarity_search(
        self,
        *,
        embedding: List[float],
        limit: int,
        score_threshold: Optional[float],
        query_filter: Optional[Filter],
        combined_filters: Dict[str, Any],
    ) -> List:
        try:
            response = self._client.query_points(
                collection_name=self.collection_name,
                query=embedding,
                with_payload=True,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
            )
            points = response.points if hasattr(response, "points") else response
            return list(points)
        except Exception as exc:
            if self._is_forbidden_error(exc):
                try:
                    response = self._client.search(
                        collection_name=self.collection_name,
                        query_vector=embedding,
                        with_payload=True,
                        limit=limit,
                        score_threshold=score_threshold,
                        query_filter=query_filter,
                    )
                    points = response if isinstance(response, list) else getattr(response, "points", response)
                    return list(points)
                except Exception as search_exc:
                    if self._needs_manual_filter(search_exc):
                        return self._manual_filter_search(
                            embedding=embedding,
                            limit=limit,
                            score_threshold=score_threshold,
                            combined_filters=combined_filters,
                        )
                    raise
            if self._needs_manual_filter(exc):
                return self._manual_filter_search(
                    embedding=embedding,
                    limit=limit,
                    score_threshold=score_threshold,
                    combined_filters=combined_filters,
                )
            raise

    # Fallback search path that filters candidate points locally.
    def _manual_filter_search(
        self,
        *,
        embedding: List[float],
        limit: int,
        score_threshold: Optional[float],
        combined_filters: Dict[str, Any],
    ) -> List:
        fetch_limit = max(limit * 5, limit)
        fetch_limit = min(fetch_limit, 100)

        response = self._client.search(
            collection_name=self.collection_name,
            query_vector=embedding,
            with_payload=True,
            limit=fetch_limit,
            score_threshold=score_threshold,
        )

        matches: List = []
        points = response if isinstance(response, list) else getattr(response, "points", response)
        for point in points:
            payload = point.payload or {}
            if self._payload_matches(payload, combined_filters):
                matches.append(point)
                if len(matches) >= limit:
                    break
        return matches

    @staticmethod
    # Basic equality check used by the manual filtering fallback.
    def _payload_matches(payload: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        if not filters:
            return True
        for key, value in filters.items():
            expected = value.get("eq") if isinstance(value, dict) else value
            if expected is None:
                continue
            if payload.get(key) != expected:
                return False
        return True


__all__ = ["DocumentStore"]
