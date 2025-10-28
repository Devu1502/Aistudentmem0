"""
Local memory utilities that mirror the high-level mem0 API but run fully offline.

This module provides:
    - LocalMemory: Qdrant-backed memory store implementing add/search/get_all/update/delete/reset.

The interface intentionally stays close to mem0.memory.main.Memory so existing FastAPI
routes in app.py can call the same methods without modification.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pytz
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

try:
    import ollama
except ImportError as exc:  
    raise RuntimeError(
        "The 'ollama' package is required for LocalOllamaEmbedder. Install it with `pip install ollama`."
    ) from exc


class LocalOllamaEmbedder:
    """Direct local embedding via Ollama without depending on mem0 factories."""

    def __init__(self, model: str = "nomic-embed-text:latest", base_url: str = "http://localhost:11434") -> None:
        self.model = model
        self.base_url = base_url
        self._client = ollama.Client(host=self.base_url)

    def embed(self, text: str) -> np.ndarray:
        """
        Generate an embedding vector for text.

        Returns a zero vector when Ollama cannot produce an embedding to keep the pipeline robust.
        """
        if not text or not text.strip():
            logger.warning("Empty text passed to embed(); returning zero vector.")
            return np.zeros(768, dtype=np.float32)

        try:
            response = self._client.embeddings(model=self.model, prompt=text)
        except Exception as err:
            logger.error("Ollama embedding request failed: %s", err)
            return np.zeros(768, dtype=np.float32)

        vector = response.get("embedding")
        if not vector:
            logger.error("Ollama returned no embedding data. Falling back to zero vector.")
            return np.zeros(768, dtype=np.float32)

        return np.array(vector, dtype=np.float32)


class LocalMemory:
    """
    Minimal offline memory manager using Qdrant + Ollama embeddings.

    Method signatures align with mem0's Memory class where the FastAPI layer relies on them.
    """

    def __init__(
        self,
        qdrant_client: Optional[QdrantClient] = None,
        embedder: Optional[LocalOllamaEmbedder] = None,
        collection_name: str = "mem0_local",
        dimension: int = 768,
        time_zone: str = "US/Pacific",
    ) -> None:
        self.collection_name = collection_name
        self.dimension = dimension
        self.time_zone = time_zone

        self.vector_store = qdrant_client or QdrantClient(url="http://localhost:6333")
        self.embedding_model = embedder or LocalOllamaEmbedder()

        self._ensure_collection()
        logger.info("LocalMemory ready (collection=%s, dimension=%s)", self.collection_name, self.dimension)

    def _ensure_collection(self) -> None:
        """Create the collection if missing, or recreate when dimension mismatch is detected."""
        try:
            info = self.vector_store.get_collection(self.collection_name)
            current_dim = info.config.params.vectors.size
            if current_dim != self.dimension:
                logger.warning(
                    "Dimension mismatch for collection %s (expected %s, got %s); recreating.",
                    self.collection_name,
                    self.dimension,
                    current_dim,
                )
                self.vector_store.delete_collection(self.collection_name)
                self._create_collection()
        except Exception:
            self._create_collection()

    def _create_collection(self) -> None:
        self.vector_store.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
        )

    @staticmethod
    def _merge_metadata(
        *,
        user_id: Optional[str],
        agent_id: Optional[str],
        run_id: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        if metadata:
            merged.update(metadata)
        if user_id:
            merged["user_id"] = user_id
        if agent_id:
            merged["agent_id"] = agent_id
        if run_id:
            merged["run_id"] = run_id
        return merged

    @staticmethod
    def _build_filters(
        *,
        user_id: Optional[str],
        agent_id: Optional[str],
        run_id: Optional[str],
        extra_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        filters: Dict[str, Any] = {}
        if user_id:
            filters["user_id"] = user_id
        if agent_id:
            filters["agent_id"] = agent_id
        if run_id:
            filters["run_id"] = run_id
        if extra_filters:
            filters.update(extra_filters)
        return filters

    @staticmethod
    def _to_qdrant_filter(filters: Dict[str, Any]) -> Optional[Filter]:
        if not filters:
            return None

        conditions: List[FieldCondition] = []
        for key, value in filters.items():
            if isinstance(value, dict):
                eq_value = value.get("eq")
                if eq_value is not None:
                    conditions.append(FieldCondition(key=key, match=MatchValue(value=eq_value)))
                else:
                    logger.warning("Unsupported nested filter for key '%s'; only 'eq' is currently handled.", key)
            else:
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))

        return Filter(must=conditions) if conditions else None

    def _now(self) -> str:
        tz = pytz.timezone(self.time_zone)
        return datetime.now(tz).isoformat()

    def add(
        self,
        text: str,
        *,
        user_id: str = "default_user",
        agent_id: str = "default_agent",
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Insert a single memory into Qdrant and return its identifier alongside stored text."""
        if not text or not text.strip():
            raise ValueError("Cannot add empty memory text.")

        embedding = self.embedding_model.embed(text)
        memory_id = str(uuid.uuid4())

        payload = self._merge_metadata(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            metadata=metadata,
        )
        payload.update(
            {
                "text": text,
                "hash": hashlib.md5(text.encode("utf-8")).hexdigest(),
                "created_at": self._now(),
                "updated_at": self._now(),
            }
        )

        point = PointStruct(id=memory_id, vector=embedding.tolist(), payload=payload)
        self.vector_store.upsert(collection_name=self.collection_name, points=[point], wait=True)

        logger.debug("Added memory %s (user=%s, agent=%s)", memory_id, user_id, agent_id)
        return {"id": memory_id, "text": text}

    def search(
        self,
        *,
        query: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        score_threshold: Optional[float] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Return similarity search results with optional metadata-based filtering."""
        embedding = self.embedding_model.embed(query)
        combined_filters = self._build_filters(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            extra_filters=filters,
        )
        qdrant_filter = self._to_qdrant_filter(combined_filters)

        results = self.vector_store.query_points(
            collection_name=self.collection_name,
            query=embedding.tolist(),
            with_payload=True,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=qdrant_filter,
        ).points

        formatted = [
            {
                "id": point.id,
                "score": point.score,
                "memory": point.payload.get("text", ""),
                "metadata": {k: v for k, v in point.payload.items() if k not in {"text"}},
            }
            for point in results
        ]

        return {"results": formatted}

    def get_all(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Retrieve all memories matching the supplied filters."""
        combined_filters = self._build_filters(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            extra_filters=filters,
        )
        qdrant_filter = self._to_qdrant_filter(combined_filters)

        collected: List[Dict[str, Any]] = []
        offset = None

        while len(collected) < limit:
            batch, offset = self.vector_store.scroll(
                collection_name=self.collection_name,
                scroll_filter=qdrant_filter,
                with_payload=True,
                limit=min(64, limit - len(collected)),
                offset=offset,
            )
            for point in batch:
                collected.append(
                    {
                        "id": point.id,
                        "memory": point.payload.get("text", ""),
                        "metadata": {k: v for k, v in point.payload.items() if k not in {"text"}},
                    }
                )
            if offset is None:
                break

        return {"results": collected}

    def update(self, memory_id: str, data: str) -> Dict[str, str]:
        """Replace the text and embedding for a stored memory."""
        if not data or not data.strip():
            raise ValueError("Cannot update a memory with empty text.")

        existing = self.vector_store.retrieve(collection_name=self.collection_name, ids=[memory_id])
        if not existing:
            raise ValueError(f"Memory with id '{memory_id}' not found.")

        embedding = self.embedding_model.embed(data)
        payload = dict(existing[0].payload or {})
        payload["text"] = data
        payload["hash"] = hashlib.md5(data.encode("utf-8")).hexdigest()
        payload["updated_at"] = self._now()

        self.vector_store.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(id=memory_id, vector=embedding.tolist(), payload=payload),
            ],
            wait=True,
        )

        return {"message": "Memory updated successfully!"}

    def delete(self, memory_id: str) -> Dict[str, str]:
        """Delete a single memory by identifier."""
        self.vector_store.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=[memory_id]),
            wait=True,
        )
        return {"message": f"Memory {memory_id} deleted successfully!"}

    def delete_all(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Delete all memories scoped by the provided identifiers."""
        combined_filters = self._build_filters(user_id=user_id, agent_id=agent_id, run_id=run_id)
        if not combined_filters:
            raise ValueError("At least one of user_id, agent_id, or run_id must be provided to delete_all.")

        qdrant_filter = self._to_qdrant_filter(combined_filters)
        self.vector_store.delete(collection_name=self.collection_name, filter=qdrant_filter, wait=True)
        return {"message": "Memories deleted successfully!"}

    def reset(self) -> Dict[str, str]:
        """Drop and recreate the underlying vector collection."""
        try:
            self.vector_store.delete_collection(self.collection_name)
        except Exception:
            logger.info("Collection %s did not exist or could not be deleted.", self.collection_name)
        self._create_collection()
        return {"message": "Memory store reset successfully!"}


__all__ = ["LocalOllamaEmbedder", "LocalMemory"]
