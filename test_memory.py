import unittest
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import numpy as np
except ImportError:  
    np = None
try:
    from qdrant_client.models import FieldCondition, Filter, MatchValue, PointIdsList, PointStruct

    qdrant_available = True
except ImportError:
    qdrant_available = False

dependencies_ready = np is not None and qdrant_available


if dependencies_ready:
    from memory import LocalMemory
else: 
    LocalMemory = None


if dependencies_ready:

    class DummyEmbedder:

        def __init__(self, dimension: int):
            self.dimension = dimension

        def embed(self, text: str) -> np.ndarray:
            seed = abs(hash(text)) % (2**32)
            rng = np.random.default_rng(seed)
            return rng.random(self.dimension, dtype=np.float32)


    class FakeQdrantClient:

        def __init__(self):
            self._collections: Dict[str, Dict[str, Any]] = {}

        def get_collection(self, collection_name: str):
            if collection_name not in self._collections:
                raise ValueError("Collection does not exist.")

            size = self._collections[collection_name]["__meta"]["size"]
            vectors = SimpleNamespace(size=size)
            params = SimpleNamespace(vectors=vectors)
            config = SimpleNamespace(params=params)
            return SimpleNamespace(config=config)

        def create_collection(self, collection_name: str, vectors_config, **_) -> None:
            self._collections[collection_name] = {
                "__meta": {"size": vectors_config.size},
                "__points": {},
            }

        def delete_collection(self, collection_name: str) -> None:
            self._collections.pop(collection_name, None)

        def upsert(self, collection_name: str, points: List[PointStruct], **_) -> None:
            collection = self._collections[collection_name]["__points"]
            for point in points:
                collection[str(point.id)] = {
                    "vector": np.array(point.vector, dtype=np.float32),
                    "payload": dict(point.payload),
                }

        def query_points(
            self,
            collection_name: str,
            query: Iterable[float],
            limit: int,
            query_filter: Optional[Filter] = None,
            **_,
        ):
            collection = self._collections[collection_name]["__points"]
            query_vector = np.array(list(query), dtype=np.float32)

            hits = []
            for pid, record in collection.items():
                if not self._matches_filter(record["payload"], query_filter):
                    continue
                score = self._cosine_similarity(query_vector, record["vector"])
                hits.append(
                    SimpleNamespace(
                        id=pid,
                        score=score,
                        payload=dict(record["payload"]),
                    )
                )

            hits.sort(key=lambda h: h.score, reverse=True)
            return SimpleNamespace(points=hits[:limit])

        def scroll(
            self,
            collection_name: str,
            scroll_filter: Optional[Filter],
            with_payload: bool,
            limit: int,
            offset=None,
        ) -> Tuple[List[SimpleNamespace], None]:
            del offset  # not needed in fake
            collection = self._collections[collection_name]["__points"]
            results = []
            for pid, record in collection.items():
                if not self._matches_filter(record["payload"], scroll_filter):
                    continue
                payload = dict(record["payload"]) if with_payload else None
                results.append(SimpleNamespace(id=pid, payload=payload))
                if len(results) >= limit:
                    break

            return results, None

        def retrieve(self, collection_name: str, ids: List[str], **_) -> List[SimpleNamespace]:
            collection = self._collections[collection_name]["__points"]
            records = []
            for pid in ids:
                record = collection.get(pid)
                if record:
                    records.append(SimpleNamespace(id=pid, payload=dict(record["payload"]), vector=record["vector"]))
            return records

        def delete(self, collection_name: str, points_selector: PointIdsList = None, filter: Filter = None, **_) -> None:
            collection = self._collections[collection_name]["__points"]
            if points_selector:
                for pid in points_selector.points:
                    collection.pop(str(pid), None)
            elif filter:
                to_delete = [
                    pid for pid, record in collection.items() if self._matches_filter(record["payload"], filter)
                ]
                for pid in to_delete:
                    collection.pop(pid, None)
            else:
                collection.clear()

        @staticmethod
        def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
            denom = float(np.linalg.norm(a) * np.linalg.norm(b))
            if denom == 0:
                return 0.0
            return float(np.dot(a, b) / denom)

        @staticmethod
        def _matches_filter(payload: Dict[str, Any], query_filter: Optional[Filter]) -> bool:
            if not query_filter:
                return True

            conditions: Iterable[FieldCondition] = getattr(query_filter, "must", []) or []
            for condition in conditions:
                value = payload.get(condition.key)
                match: Optional[MatchValue] = getattr(condition, "match", None)
                if match is not None and value != match.value:
                    return False
            return True


if dependencies_ready:

    class LocalMemoryTests(unittest.TestCase):
        def setUp(self) -> None:
            self.embed_dim = 16
            self.client = FakeQdrantClient()
            self.memory = LocalMemory(
                qdrant_client=self.client,
                embedder=DummyEmbedder(self.embed_dim),
                collection_name="unit_test_collection",
                dimension=self.embed_dim,
            )

        def test_add_and_search(self):
            added = self.memory.add("Algebra basics", user_id="u1", agent_id="math")
            result = self.memory.search(query="Algebra basics", user_id="u1", agent_id="math")

            self.assertEqual(len(result["results"]), 1)
            self.assertEqual(result["results"][0]["id"], added["id"])
            self.assertEqual(result["results"][0]["memory"], "Algebra basics")

        def test_get_all_filters_by_user(self):
            self.memory.add("Physics note", user_id="u1", agent_id="science")
            self.memory.add("History outline", user_id="u2", agent_id="social")

            result_u1 = self.memory.get_all(user_id="u1")
            self.assertEqual(len(result_u1["results"]), 1)
            self.assertEqual(result_u1["results"][0]["memory"], "Physics note")

        def test_update_replaces_text(self):
            added = self.memory.add("Draft fact", user_id="u1")
            self.memory.update(added["id"], "Refined fact")

            result = self.memory.search(query="Refined fact", user_id="u1")
            self.assertEqual(result["results"][0]["memory"], "Refined fact")

        def test_delete_and_delete_all(self):
            first = self.memory.add("Keep this", user_id="u1")
            second = self.memory.add("Remove this", user_id="u1")

            self.memory.delete(second["id"])
            remaining = self.memory.get_all(user_id="u1")["results"]
            ids = {item["id"] for item in remaining}
            self.assertIn(first["id"], ids)
            self.assertNotIn(second["id"], ids)

            self.memory.delete_all(user_id="u1")
            after_clear = self.memory.get_all(user_id="u1")["results"]
            self.assertEqual(after_clear, [])

        def test_reset_clears_collection(self):
            self.memory.add("Temporary memory", user_id="u1")
            self.memory.reset()
            after_reset = self.memory.get_all(user_id="u1")["results"]
            self.assertEqual(after_reset, [])

else:

    class LocalMemoryTests(unittest.TestCase):
        @unittest.skip("numpy and qdrant-client are required for LocalMemory tests")
        def test_requires_numpy(self):
            pass


if __name__ == "__main__":
    unittest.main()
