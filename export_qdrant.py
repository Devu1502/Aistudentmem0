from qdrant_client import QdrantClient
import csv

# Connect to local Qdrant instance
qdrant = QdrantClient(url="http://localhost:6333")

# Scroll through all points in the mem0_local collection
points, _ = qdrant.scroll(
    collection_name="mem0_local",
    with_payload=True,
    with_vectors=True,
    limit=1000
)

# Write everything to CSV
with open("qdrant_mem0_local.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["id", "text", "user_id", "agent_id", "run_id", "type", "created_at", "vector_preview"])

    for p in points:
        payload = p.payload or {}
        vector = getattr(p, "vector", [])
        writer.writerow([
            p.id,
            payload.get("text", ""),
            payload.get("user_id", ""),
            payload.get("agent_id", ""),
            payload.get("run_id", ""),
            payload.get("type", ""),
            payload.get("created_at", ""),
            str(vector[:10])  # only first 10 for readability
        ])

print("Exported mem0_local to qdrant_mem0_local.csv successfully.")
