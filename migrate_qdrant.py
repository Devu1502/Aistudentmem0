"""
Utility script to migrate existing local Qdrant collections to Qdrant Cloud.

Run once after configuring config/settings.py (or environment variables) with the
target cluster URL/API key. The script paginates through every point in the local
collections and upserts them into the remote cluster, recreating the collections
there to match the expected vector size/distance.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional, Tuple

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config.settings import settings


LOCAL_QDRANT_URL = os.getenv("LOCAL_QDRANT_URL", "http://localhost:6333")
COLLECTIONS = ("mem0_local", "mem0_documents")
SCROLL_BATCH_SIZE = 256


def _ensure_remote_collection(local: QdrantClient, remote: QdrantClient, name: str) -> None:
    try:
        info = local.get_collection(name)
        vector_params = info.config.params.vectors
        size = getattr(vector_params, "size", settings.vectors.embedding_dim)
        distance_str = str(getattr(vector_params, "distance", Distance.COSINE)).lower()
        distance = Distance.COSINE
        if "dot" in distance_str:
            distance = Distance.DOT
        elif "euclid" in distance_str:
            distance = Distance.EUCLID

        remote.recreate_collection(
            collection_name=name,
            vectors_config=VectorParams(size=size, distance=distance),
        )
        print(f"  • Remote collection '{name}' ensured (size={size}, distance={distance.value}).")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! Unable to inspect local collection {name}: {exc}")
        raise


def _convert_points(batch: Iterable) -> list[PointStruct]:
    converted: list[PointStruct] = []
    for point in batch:
        vector = getattr(point, "vector", None)
        payload = getattr(point, "payload", None)
        if vector is None or payload is None:
            continue
        if hasattr(vector, "tolist"):
            vector = vector.tolist()
        converted.append(PointStruct(id=point.id, vector=vector, payload=payload))
    return converted


def _scroll_points(
    client: QdrantClient,
    collection: str,
    offset: Optional[str] = None,
) -> Tuple[list, Optional[str]]:
    points, next_offset = client.scroll(
        collection_name=collection,
        limit=SCROLL_BATCH_SIZE,
        with_payload=True,
        with_vectors=True,
        offset=offset,
    )
    return points, next_offset


def migrate() -> None:
    local = QdrantClient(url=LOCAL_QDRANT_URL, prefer_grpc=False)
    remote = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        prefer_grpc=False,
    )

    print("Starting migration to Qdrant Cloud…")
    for collection in COLLECTIONS:
        print(f"\n=== {collection} ===")
        _ensure_remote_collection(local, remote, collection)

        offset: Optional[str] = None
        total_uploaded = 0

        while True:
            batch, offset = _scroll_points(local, collection, offset=offset)
            if not batch:
                break
            payload = _convert_points(batch)
            if not payload:
                continue
            remote.upsert(collection_name=collection, points=payload, wait=True)
            total_uploaded += len(payload)
            print(f"  Uploaded {total_uploaded} points so far…")

            if offset is None:
                break

        print(f"  Finished collection '{collection}' with {total_uploaded} points migrated.")

    print("\nDone! Verify counts via the Qdrant Cloud dashboard or API.")


if __name__ == "__main__":
    migrate()
