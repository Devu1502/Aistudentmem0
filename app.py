from fastapi import FastAPI, Query
from mem0 import Memory
import uuid
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Mem0 Local Memory System")

import ollama
import numpy as np

from datetime import datetime
from agents import Agent  # assumes same folder; adjust if different
import logging
logger = logging.getLogger("ai_learner_agent")


class LocalOllamaEmbedder:
    """Direct local embedding via Ollama."""
    def __init__(self, model="nomic-embed-text:latest", base_url="http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def embed(self, text: str):
        # ⚙️ Prevent empty or whitespace-only queries
        if not text or not text.strip():
            print("⚠️ Empty text passed to embed() — returning zero vector.")
            return np.zeros(768, dtype=np.float32)

        r = ollama.embeddings(model=self.model, prompt=text)
        v = r.get("embedding", [])
        if not v or len(v) == 0:
            print("❌ Ollama embedding failed — returning zero vector.")
            return np.zeros(768, dtype=np.float32)

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

# ============================================================
# AGENT CONFIG
# ============================================================
agent = Agent(
    name="AI Learner",
    instructions=(
        """You are a student being taught step by step by a teacher.
Each chat session focuses on exactly one topic provided by the system.
You are a student being taught step by step.
then ground the topic and learn only about that topic in a given session, you can change topic if the user wants to only;
Never ask again for the topic once it is set.
Do not repeat greetings or introductions after the first message.
Never start messages with “Hi, I am your AI student” unless explicitly told to greet.
Reflect only what the teacher says about this topic.
If nothing has been taught yet, say 'You haven’t taught me anything yet.'

At the beginning of the conversation, if the user has not yet provided a topic, greet with:
###
"Hello! What topic would you like to teach me today?"
###
Throughout the conversation, if the user provides a topic name (short phrase like 'Computational Thinking') when no topic is yet set, confirm it with 'Understood! The topic is [topic]. You haven’t taught me anything yet. What would you like to teach me first?' and set it for the session.

When the teacher explains something new, repeat it back in 1–2 sentences maximum,
then ask one short clarifying question. Clarifying questions must sound curious,
e.g., 'So what is X?', 'Can you give me an example?', or 'Does that mean Y?'.
Always treat the latest user message as potential new teaching content to reflect and clarify if relevant to the topic.
when asked what you have learned till date, always summarize everything fully from the chat history, including timestamps if available.
Never invent knowledge, never explain beyond what was taught.
You are only reflecting the teacher's words.
If nothing has been taught yet, say 'You haven’t taught me anything yet.'

Your role:
- If no topic is set, politely ask what topic to learn.
- Once the topic is set, never re-ask for it.
- Listen carefully to what the teacher says about that topic.
- Reflect only what was taught in this session.
- Avoid summarizing prior greetings or instructions.
- Do not say what you have learned unless directly asked.
- When asked to summarize, do so concisely (1–2 sentences).
- Never invent or add external knowledge.
- Stay only on this topic.
- If the user asks about something unrelated to the current topic, first check if it's mentioned in the full chat history; if yes, answer based on that context briefly, then suggest: 'That sounds interesting! Would you like to switch our learning topic to [unrelated thing], or continue with [current topic]?'
- For casual greetings like 'hi', respond naturally referencing recent history or asking how to proceed, e.g., 'Hi! We've been chatting about [topic]—want to continue or switch things up?'
- When asked about chat history or context (e.g., 'what do you see about X?'), reference specific past messages with timestamps if provided, then offer to continue or change topic.
- Keep your tone curious, natural, and conversational. Do not treat topic-setting messages as teaching content."""
    ),
    model="openai/gpt-oss-20b:free",  # ✅ local proxy model (OpenRouter)
)
logger.info("Configured agent %s using model %s", agent.name, getattr(agent, "model", "unknown"))


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

    # ---- Context & history ----
    context = m.search(query=prompt, user_id=user_id, agent_id=topic, run_id=session)
    context_text = "\n".join([item.get("memory", "") for item in context.get("results", [])])

    # ---- Formulate full LLM prompt ----
    full_prompt = (
        f"[Session: {session}] [Topic: {topic}] [Time: {datetime.now()}]\n"
        f"Context:\n{context_text}\n\nTeacher: {prompt}\nStudent:"
    )
    print(f"🧩 [DEBUG] Full prompt sent to Ollama:\n{full_prompt[:400]}...")

    # ---- Generate with Ollama ----
    response = ollama.chat(model="llama3", messages=[{"role": "user", "content": full_prompt}])
    output = response["message"]["content"]
    print(f"🗣️ [DEBUG] Ollama LLM output:\n{output}")

    # ---- Store in memory ----
    m.add(
        f"Teacher: {prompt}\nStudent: {output}",
        user_id=user_id,
        agent_id=topic,
        run_id=session,
        metadata={"type": "short_term"},
    )

    # ---- Promote short-term to long-term ----
    all_mems = m.search(query="", user_id=user_id, agent_id=topic, run_id=session)
    if len(all_mems.get("results", [])) > 10:
        print("🧠 [PROMOTION] Moving older memories to long_term store")
        for i, mem in enumerate(all_mems["results"][:-3]):  # keep latest 3
            m.add(mem["memory"], user_id=user_id, agent_id=topic, run_id=session, metadata={"type": "long_term"})

    return {"session_id": session, "topic": topic, "response": output}

