import csv, json
from qdrant_client import QdrantClient

# Connect to local Qdrant
q = QdrantClient(url="http://localhost:6333")

# Retrieve all points with payloads + vectors
points, _ = q.scroll(
    collection_name="mem0_local",
    with_payload=True,
    with_vectors=True,
    limit=2000  # adjust if you have more points
)

# Write to CSV
with open("mem0_local_vectors.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["id", "text", "metadata", "vector_first_chars"])
    for p in points:
        text = (p.payload.get("text") or "").replace("\n", " ")[:200]  # shorten text
        metadata = json.dumps({k: v for k, v in p.payload.items() if k != "text"})
        # shorten vector for readability but keep first few digits
        vector_snippet = json.dumps([round(v, 4) for v in p.vector[:8]]) + "..."
        writer.writerow([p.id, text, metadata, vector_snippet])

print("Export complete -> mem0_local_vectors.csv")
