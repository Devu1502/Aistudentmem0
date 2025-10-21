from fastapi import FastAPI, Query
from mem0 import Memory
import uuid
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Mem0 Local Memory System")

import ollama
import numpy as np

class LocalOllamaEmbedder:
    """Direct local embedding via Ollama."""
    def __init__(self, model="nomic-embed-text:latest", base_url="http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def embed(self, text: str):
        r = ollama.embeddings(model=self.model, prompt=text)
        v = r.get("embedding", [])
        if not v or len(v) == 0:
            raise ValueError("❌ Ollama embedding failed — got empty vector")
        return np.array(v, dtype=np.float32)


# ✅ Allow the React UI to call the API from port 3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Fully local Mem0 setup (no OpenAI dependency)
from qdrant_client import QdrantClient
from mem0.memory.main import Memory


# ✅ Manual lightweight subclass that avoids OpenAI factory
from qdrant_client.models import PointStruct
import uuid

class LocalMemory:
    """Minimal offline memory manager using Qdrant + Ollama embeddings."""

    def __init__(self, qdrant_client, embedder):
        self.vector_store = qdrant_client
        self.embedding_model = embedder
        self.collection_name = "mem0_local"
        self.dimension = 768
        self._ensure_collection()
        print("🧠 LocalMemory initialized — fully offline mode")

    def _ensure_collection(self):
        """Create collection if missing or mismatched."""
        from qdrant_client.models import Distance, VectorParams
        try:
            info = self.vector_store.get_collection(self.collection_name)
            dims = info.config.params.vectors.size
            if dims != self.dimension:
                print(f"⚠️ Dimension mismatch ({dims} vs {self.dimension}); recreating.")
                self.vector_store.delete_collection(self.collection_name)
                self.vector_store.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
                )
        except Exception:
            self.vector_store.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
            )

    def add(self, text: str, user_id="sree", agent_id="general", run_id=None, metadata=None):
        """Add one memory record with embedding."""
        vec = self.embedding_model.embed(text)
        pid = str(uuid.uuid4())
        payload = {"text": text, "user_id": user_id, "agent_id": agent_id, "run_id": run_id or "default"}
        if metadata:
            payload.update(metadata)

        self.vector_store.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=pid, vector=vec.tolist(), payload=payload)],
            wait=True,
        )
        print(f"🧠 Added memory {pid[:8]} | {text[:40]}")
        return {"id": pid, "text": text}

    def search(self, query, user_id=None, agent_id=None, run_id=None, filters=None):
        """Search for similar memories."""
        qvec = self.embedding_model.embed(query)
        res = self.vector_store.query_points(
            collection_name=self.collection_name,
            query=qvec.tolist(),
            with_payload=True,
            limit=5,
        ).points
        return {"results": [{"id": p.id, "score": p.score, "memory": p.payload.get("text", "")} for p in res]}


# ✅ Qdrant and local embedder setup
qdrant = QdrantClient(url="http://localhost:6333")
local_embedder = LocalOllamaEmbedder()
m = LocalMemory(qdrant, local_embedder)


# -----------------------------------------------------------
# CONFIGURATION: Local Qdrant + Ollama
# -----------------------------------------------------------
config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "collection_name": "mem0_local",
            "host": "localhost",
            "port": 6333,
            "embedding_model_dims": 768,
        },
    },
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "llama3:latest",
            "temperature": 0,
            "max_tokens": 1000,
            "ollama_base_url": "http://localhost:11434",
        },
    },
    "embedder": {
        "provider": "ollama",
        "config": {
            "model": "nomic-embed-text:latest",
            "ollama_base_url": "http://localhost:11434",
        },
    },
}


# -----------------------------------------------------------
# MEMORY HELPERS
# -----------------------------------------------------------
def get_session_id(session_id: str | None):
    """Auto-generate session if not provided."""
    return session_id or str(uuid.uuid4())

# -----------------------------------------------------------
# BASIC ROUTES
# -----------------------------------------------------------

@app.get("/")
def root():
    return {"message": "Mem0 + Ollama + Qdrant fully local memory server running"}

# 🧠 Add new memory (auto-routes to short/long/episodic)
@app.post("/add")
def add_memory(
    text: str = Query(..., description="Content to store"),
    user_id: str = "sree",
    topic: str = "general",
    session_id: str | None = None,
    memory_type: str = "short_term",
):
    session = get_session_id(session_id)
    result = m.add(
        text,
        user_id=user_id,
        agent_id=topic,
        run_id=session,
        metadata={"type": memory_type},
    )
    print("\n🧠 [DEBUG] Added memory:")
    print(result)
    return {"session_id": session, "added": result}


# 🔍 Search similar memories
@app.get("/search")
def search_memory(
    query: str,
    user_id: str = "sree",
    topic: str | None = None,
    session_id: str | None = None,
    memory_type: str | None = None,
):
    filters = {}
    if memory_type:
        filters["type"] = memory_type

    results = m.search(
        query=query,
        user_id=user_id,
        agent_id=topic,
        run_id=session_id,
        filters=filters,
    )
    return {"query": query, "results": results}

# 🗂️ Get all memories (with optional filters)
# 🧠 Add new memory (auto-routes to short/long/episodic)
@app.post("/add")
def add_memory(
    text: str = Query(..., description="Content to store"),
    user_id: str = "sree",
    topic: str = "general",
    session_id: str | None = None,
    memory_type: str = "short_term",
):
    session = get_session_id(session_id)
    result = m.add(
        text,
        user_id=user_id,
        agent_id=topic,
        run_id=session,
        metadata={"type": memory_type},
    )
    print("\n🧠 [DEBUG] Added memory:")
    print(result)
    return {"session_id": session, "added": result}


# 🗂️ Get all memories (with optional filters)
@app.get("/all")
def get_all(
    user_id: str = "sree",
    topic: str | None = None,
    session_id: str | None = None,
):
    raw = m.get_all(user_id=user_id, agent_id=topic, run_id=session_id)
    # raw appears to be a dict with key "results"
    results = raw.get("results") if isinstance(raw, dict) else raw
    if results is None:
        results = []
    print("\n📜 [DEBUG] formatted results array:", results)
    return {"memories": results}


# ✏️ Update a specific memory
@app.post("/update")
def update_memory(
    memory_id: str,
    new_text: str,
):
    result = m.update(memory_id=memory_id, data=new_text)
    return {"updated": result}

# 🗑️ Delete specific memory or all by user
@app.delete("/delete")
def delete_memory(
    memory_id: str | None = None,
    user_id: str | None = None,
):
    if memory_id:
        m.delete(memory_id=memory_id)
        return {"deleted_id": memory_id}
    if user_id:
        m.delete_all(user_id=user_id)
        return {"deleted_all_for_user": user_id}
    return {"error": "Provide either memory_id or user_id"}

# 🔄 Reset entire memory store
@app.post("/reset")
def reset_all():
    m.reset()
    return {"message": "All memories reset"}

import ollama

@app.post("/chat")
def chat(
    prompt: str = Query(...),
    user_id: str = "sree",
    topic: str = "general",
    session_id: str | None = None,
):
    session = get_session_id(session_id)
    print(f"\n💬 [DEBUG] Chat request: {prompt}")

    # Retrieve relevant context
    context = m.search(query=prompt, user_id=user_id, agent_id=topic, run_id=session)
    context_text = "\n".join([item.get("memory", "") for item in context.get("results", [])])

    full_prompt = f"Context:\n{context_text}\n\nUser: {prompt}\nAssistant:"
    print(f"🧩 [DEBUG] Full prompt sent to Ollama:\n{full_prompt[:400]}...")

    # ✅ Local Ollama chat
    response = ollama.chat(
        model="llama3",
        messages=[{"role": "user", "content": full_prompt}],
    )

    output = response["message"]["content"]
    print(f"🗣️ [DEBUG] Ollama LLM output:\n{output}")

    # Store interaction as text so the embedder receives a flat string
    conversation_summary = f"User: {prompt}\nAssistant: {output}"
    m.add(
        conversation_summary,
        user_id=user_id,
        agent_id=topic,
        run_id=session,
        metadata={"type": "short_term"},
    )

    return {"session_id": session, "response": output}
