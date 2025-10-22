"""
Document storage and retrieval utilities backed by Qdrant.

This module keeps the logic for handling uploaded documents separate from the
core conversational memory so it can be swapped to a remote Qdrant instance
without touching the FastAPI routes.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from memory import LocalOllamaEmbedder

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
        embedder: Optional[LocalOllamaEmbedder] = None,
        collection_name: str = "mem0_documents",
        dimension: int = 768,
        distance: Distance = Distance.COSINE,
    ) -> None:
        self.collection_name = collection_name
        self.dimension = dimension
        self._client = qdrant_client or QdrantClient(url="http://localhost:6333")
        self._embedder = embedder or LocalOllamaEmbedder()
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
                self._client.delete_collection(self.collection_name)
                self._create_collection()
        except Exception:
            self._create_collection()

    def _create_collection(self) -> None:
        self._client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.dimension, distance=self._distance),
        )

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
        hits = self._client.query_points(
            collection_name=self.collection_name,
            query=vector.tolist(),
            with_payload=True,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=query_filter,
        ).points

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


__all__ = ["DocumentStore"]
