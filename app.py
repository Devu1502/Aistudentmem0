from fastapi import FastAPI, Query, Request, HTTPException, UploadFile, File
import uuid
from fastapi.middleware.cors import CORSMiddleware
from intent_utils import detect_dev_command, handle_system_action, sanitize_reply
from memory import LocalMemory, LocalOllamaEmbedder
from teach_mode import is_teach_mode_on, set_teach_mode
from doc_store import DocumentStore

app = FastAPI(title="Mem0 Local Memory System")
# Must come immediately after FastAPI initialization
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import ollama
from markitdown import MarkItDown

from datetime import datetime
from agents import Agent  # assumes same folder; adjust if different
import logging
logger = logging.getLogger("ai_learner_agent")


# ✅ Fully local Mem0 setup (no OpenAI dependency)
from qdrant_client import QdrantClient


# ✅ Qdrant and local embedder setup
qdrant = QdrantClient(url="http://localhost:6333")
local_embedder = LocalOllamaEmbedder()
m = LocalMemory(qdrant, local_embedder)
document_store = DocumentStore(qdrant, local_embedder)

from dotenv import load_dotenv
import os
import tempfile
from typing import List, Dict, Any

# Load environment variables from .env
load_dotenv("/Users/sreekanthgopi/Desktop/Apps/AIStudentMem0/.env")

if not os.getenv("OPENAI_API_KEY"):
    raise EnvironmentError("❌ OPENAI_API_KEY not found in environment!")


# AGENT CONFIG
agent = Agent(
    name="AI Learner",
    instructions=(
        """You are a friendly AI buddy who learns and reflects through chat.
You respond naturally, focusing on what the teacher says or what is already present in the chat or referenced documents.
You do not use model knowledge outside of what’s given in the context (temperature = 0).

At the start of the new chat, greet once naturally:
"I’m your AI buddy! What would you like to teach me today?"
This is not to be repeated later if it is not the first chat in the new chat.

During the conversation:
- Treat the latest user message as potential new teaching content or question.
- When the teacher explains something new, respond concisely with a short acknowledgment like “Understood!” or “Got it!” and a brief summary if needed.
- Reflect only what the teacher says or what’s already available in the conversation or reference docs.
- You may answer user questions that refer to any previous chat context, topic, or information found in documents or memory.
- If something isn’t found in the context or history, say “Nothing has been taught yet on this content as I checked our past chats.”
- Avoid asking for topics again; respond smoothly even if no topic is set.
- Stay conversational, natural, and curious, but concise.
- When asked to summarize, do so briefly and clearly.

Special instructions for new topic/session management:
- If the teacher says to change topic, use:
  <system_action>topic=NEW_TOPIC</system_action>
- If the teacher says to start a new session, use:
  <system_action>session=new</system_action>
- If the teacher says to clear memory or reset, use:
  <system_action>reset</system_action>
- If both are requested together (e.g., “new topic and new session”), use:
  <system_action>session=new;topic=NEW_TOPIC</system_action>
- Only apply these actions if the teacher explicitly uses the word “NEW”.

Always keep tone conversational, polite, and focused on the user’s input and prior context.
"""
    ),
    model="gpt-5-nano",
)
logger.info("Configured agent %s using model %s", agent.name, getattr(agent, "model", "unknown"))


# model="openai/gpt-oss-20b:free",  # ✅ local proxy model (OpenRouter)
    # model="gpt-4.1",
    # model="ollama/llama3:latest",  # local Ollama model

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

import sqlite3
from datetime import datetime

def log_message(session_id, topic, user_role, message):
    con = sqlite3.connect("chat_history_memori.db")
    cur = con.cursor()
    cur.execute("INSERT INTO chat_history (session_id, topic, user_role, message) VALUES (?,?,?,?)",
                (session_id, topic, user_role, message))
    con.commit()
    con.close()

def start_session(topic="general"):
    sid = str(uuid.uuid4())
    con = sqlite3.connect("chat_history_memori.db")
    cur = con.cursor()
    cur.execute("INSERT INTO session_meta (session_id, topic, started_at) VALUES (?,?,?)",
                (sid, topic, datetime.now()))
    con.commit()
    con.close()
    return sid

def end_session(session_id, summary=""):
    con = sqlite3.connect("chat_history_memori.db")
    cur = con.cursor()
    cur.execute("UPDATE session_meta SET ended_at=?, summary=? WHERE session_id=?",
                (datetime.now(), summary, session_id))
    con.commit()
    con.close()

def ensure_session_tables(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_meta (
            session_id TEXT PRIMARY KEY
        );
        """
    )
    conn.commit()

    cur = conn.execute("PRAGMA table_info(session_meta)")
    existing_columns = {row[1] for row in cur.fetchall()}

    required_columns = {
        "title": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }
    for column, col_type in required_columns.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE session_meta ADD COLUMN {column} {col_type}")
    conn.commit()


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


@app.get("/teach_mode")
def get_teach_mode():
    return {"teach_mode": is_teach_mode_on()}


@app.post("/teach_mode")
def update_teach_mode(enabled: bool = Query(..., description="Enable or disable Teach Mode")):
    state = set_teach_mode(enabled)
    return {"teach_mode": state}


@app.post("/documents/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > 5:
        raise HTTPException(status_code=400, detail="Upload up to five files at a time.")

    md = MarkItDown(enable_plugins=False)
    uploaded: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for file in files:
        suffix = os.path.splitext(file.filename or "document")[1] or ".bin"
        try:
            contents = await file.read()
            if not contents:
                raise ValueError("Empty file.")

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(contents)
                tmp_path = tmp.name

            try:
                result = md.convert(tmp_path)
                text_content = (result.text_content or "").strip()
                if not text_content:
                    raise ValueError("No text extracted from document.")

                metadata = {
                    "filename": file.filename,
                    "content_type": file.content_type,
                    "uploaded_at": datetime.utcnow().isoformat(),
                }
                store_result = document_store.add_document(file.filename or "Untitled", text_content, metadata=metadata)
                uploaded.append(
                    {
                        "filename": file.filename,
                        "doc_id": store_result["doc_id"],
                        "chunks": store_result["chunks"],
                    }
                )
            finally:
                os.remove(tmp_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to ingest document %s", file.filename)
            errors.append({"filename": file.filename, "error": str(exc)})

    if not uploaded and errors:
        raise HTTPException(status_code=500, detail={"errors": errors})

    return {"uploaded": uploaded, "errors": errors}


@app.get("/sidebar_sessions")
def sidebar_sessions():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        ensure_session_tables(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT ch.session_id,
                   COALESCE(sm.title, '') AS title,
                   MAX(ch.timestamp) AS last_time
            FROM chat_history ch
            LEFT JOIN session_meta sm ON sm.session_id = ch.session_id
            GROUP BY ch.session_id
            ORDER BY last_time DESC
        """)
        sessions = []
        for row in cur.fetchall():
            session_id = row["session_id"]
            cur.execute(
                "SELECT user_input, ai_output, timestamp FROM chat_history WHERE session_id=? ORDER BY id DESC LIMIT 1",
                (session_id,),
            )
            last_msg = cur.fetchone()
            preview = ""
            if last_msg:
                preview = last_msg["user_input"] or last_msg["ai_output"] or ""

            sessions.append(
                {
                    "session_id": session_id,
                    "title": row["title"],
                    "last_message_time": row["last_time"],
                    "preview": preview,
                }
            )
        return {"sessions": sessions}
    finally:
        conn.close()


@app.delete("/delete_session")
def delete_session(session_id: str = Query(...)):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        ensure_session_tables(conn)
        cur = conn.cursor()
        cur.execute("DELETE FROM chat_history WHERE session_id=?", (session_id,))
        cur.execute("DELETE FROM session_meta WHERE session_id=?", (session_id,))
        conn.commit()
        return {"message": f"Session {session_id} deleted."}
    finally:
        conn.close()


@app.post("/rename_session")
def rename_session(session_id: str = Query(...), new_name: str = Query(...)):
    if not new_name.strip():
        raise HTTPException(status_code=400, detail="new_name cannot be empty.")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        ensure_session_tables(conn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO session_meta (session_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                title=excluded.title,
                updated_at=excluded.updated_at
            """,
            (session_id, new_name.strip(), datetime.utcnow().isoformat(), datetime.utcnow().isoformat()),
        )
        conn.commit()
        return {"message": f"Session {session_id} renamed."}
    finally:
        conn.close()


@app.get("/session_messages")
def session_messages(session_id: str = Query(...)):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_input, ai_output, timestamp FROM chat_history WHERE session_id=? ORDER BY id ASC",
            (session_id,),
        )
        rows = cur.fetchall()
        messages = []
        for row in rows:
            if row["user_input"]:
                messages.append(
                    {"role": "teacher", "content": row["user_input"], "timestamp": row["timestamp"]}
                )
            if row["ai_output"]:
                messages.append(
                    {"role": "assistant", "content": row["ai_output"], "timestamp": row["timestamp"]}
                )
        return {"messages": messages}
    finally:
        conn.close()

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
import traceback

DB_PATH = "/Users/sreekanthgopi/Desktop/Apps/AIStudentMem0/chat_history_memori.db"

from agents import Runner
import traceback
import uuid
import sqlite3
from datetime import datetime

@app.post("/chat")
async def chat(request: Request, prompt: str, session_id: str | None = None):
    """
    Handles chat messages asynchronously:
      • Uses Runner.run() (async-safe)
      • Maintains DB + memory consistency
      • Returns structured response
    """
    conn: sqlite3.Connection | None = None
    teach_on = is_teach_mode_on()
    print(f"🎓 Teach Mode is {'ON' if teach_on else 'OFF'}")
    try:
        # --- 0️⃣ Ensure session_id ---
        if not session_id:
            session_id = str(uuid.uuid4())
            print(f"🆕 Generated new session_id: {session_id}")

        # --- 0️⃣.5 Developer slash commands ---
        dev_cmd = detect_dev_command(prompt)
        if dev_cmd:
            if dev_cmd["cmd"] == "search_topic":
                query = dev_cmd["arg"]
                print(f"🛠️ Dev command detected: /search_topic '{query}'")
                results = m.search(query=query, user_id="sree")
                return {
                    "response": f"🔍 Found {len(results.get('results', []))} results for '{query}'",
                    "session_id": session_id,
                }
            if dev_cmd["cmd"] == "reset":
                print("🛠️ Dev command detected: /reset")
                m.reset()
                return {"response": "🧹 Memory store reset successfully.", "session_id": session_id}

        # --- 1️⃣ Connect to SQLite ---
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cur = conn.cursor()
        print(f"✅ Opened DB connection for session {session_id}")
        ensure_session_tables(conn)

        # --- 2️⃣ Ensure table exists ---
        cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            user_input TEXT,
            ai_output TEXT,
            timestamp TEXT
        );
        """)
        conn.commit()

        # --- 3️⃣ Fetch previous context ---
        if teach_on:
            rows = []
            chat_context = ""
            print("🧠 Teach Mode active — skipping chat history aggregation.")
        else:
            cur.execute(
                "SELECT user_input, ai_output FROM chat_history WHERE session_id=? ORDER BY id ASC;",
                (session_id,),
            )
            rows = cur.fetchall()
            chat_context = "\n".join(
                [f"Teacher: {r[0]}\nStudent: {r[1]}" for r in rows if r[0] or r[1]]
            )
            print(f"🧠 Loaded {len(rows)} previous messages for context.")

        # --- 3️⃣.5 Fetch related memories from Qdrant ---
        if not teach_on:
            try:
                def extract_hits(result):
                    return result.get("results", []) if isinstance(result, dict) else (result or [])

                session_hits = extract_hits(
                    m.search(query=prompt, user_id="sree", agent_id="general", run_id=session_id)
                )
                combined_hits = session_hits[:]

                if len(combined_hits) < 5:
                    global_hits = extract_hits(m.search(query=prompt, user_id="sree", agent_id="general"))
                    seen_ids = {item.get("id") for item in combined_hits}
                    for item in global_hits:
                        if item.get("id") not in seen_ids:
                            combined_hits.append(item)
                            seen_ids.add(item.get("id"))

                if combined_hits:
                    print("📂 Vector search hits:")
                    for idx, item in enumerate(combined_hits[:5]):
                        score = item.get("score")
                        mem_text = item.get("memory", "")
                        score_display = f"{score:.3f}" if isinstance(score, (int, float)) else score
                        print(f"  {idx + 1}. score={score_display} text={mem_text[:500]}")
                else:
                    print("📂 Vector search hits: none")

                similar_memories = [r["memory"] for r in combined_hits if r.get("score", 0) > 0.2]
                memory_context = "\n".join(similar_memories)
                if memory_context:
                    print(f"📚 Retrieved {len(similar_memories)} related memories from vector store.")
                    chat_context += f"\n\n[Relevant Past Knowledge]\n{memory_context}"
            except Exception as search_err:
                print("⚠️ Memory search failed:", search_err)
        else:
            print("📂 Teach Mode active — skipping vector memory retrieval.")

        # --- 3️⃣.6 Fetch uploaded document knowledge ---
        if not teach_on:
            try:
                doc_results = document_store.search(prompt, limit=5)
                doc_hits = doc_results.get("results", [])
                if doc_hits:
                    print("📑 Document hits:")
                    doc_context_lines: List[str] = []
                    for idx, item in enumerate(doc_hits[:3]):
                        score = item.get("score")
                        meta = item.get("metadata", {})
                        title = meta.get("title") or meta.get("filename") or "Document"
                        snippet = (item.get("memory") or "").strip()
                        score_display = f"{score:.3f}" if isinstance(score, (int, float)) else score
                        print(f"  {idx + 1}. score={score_display} title={title}")
                        doc_context_lines.append(f"{title}:\n{snippet}")

                    if doc_context_lines:
                        print("🧾 Appending document context:")
                        for preview in doc_context_lines:
                            trimmed = preview.replace("\n", " ")
                            print(f"    └ {trimmed[:160]}{'…' if len(trimmed) > 160 else ''}")
                        doc_context = "\n\n".join(doc_context_lines)
                        chat_context += f"\n\n[Uploaded Document Context]\n{doc_context}"
                else:
                    print("📑 Document hits: none")
            except Exception as doc_err:  # noqa: BLE001
                print("⚠️ Document retrieval failed:", doc_err)
        else:
            print("📑 Teach Mode active — skipping document retrieval.")

        # --- 4️⃣ Run Agent asynchronously ---
        try:
            print("🤖 Calling OpenAI Agent (async)...")
            user_prompt = (
                f"[Session: {session_id}] [TeachMode: {'ON' if teach_on else 'OFF'}]\n"
                f"[Time: {datetime.now().isoformat()}]\n"
                f"Context:\n{chat_context if not teach_on else ''}\n\nTeacher: {prompt}\nStudent:"
            )
            preview_context = "" if teach_on else chat_context
            print(f"🧾 LLM context preview (first 1000 chars):\n{preview_context[:5000]}")

            result = await Runner.run(agent, user_prompt)
            raw_reply = getattr(result, "final_output", "")
            print(f"📝 Raw LLM reply: {raw_reply!r}")
            if teach_on:
                reply = " "
            else:
                reply = raw_reply.strip()
                if not reply:
                    reply = "⚠️ Agent returned no output."

            reply, action_data = sanitize_reply(reply)
            if action_data:
                print(f"🧭 Parsed system action: {action_data}")
                sys_reply, _ = handle_system_action(action_data, session_id, m)
                if sys_reply:
                    print(f"⚙️ System action executed: {action_data}")
                    return {"response": sys_reply, "session_id": session_id}
        except Exception as agent_err:
            print("❌ Agent execution failed:", agent_err)
            traceback.print_exc()
            return {"detail": f"Agent execution failed: {agent_err}"}

        # --- 5️⃣ Store in local memory ---
        conversation_summary = f"Teacher: {prompt}\nStudent: {reply}"
        print(f"🧠 Storing short-term memory snippet:\n{conversation_summary[:300]}")
        m.add(
            conversation_summary,
            user_id="sree",
            agent_id="general",
            run_id=session_id,
            metadata={"type": "short_term"},
        )

        # --- 6️⃣ Insert into DB ---
        cur.execute(
            "INSERT INTO chat_history (session_id, user_input, ai_output, timestamp) VALUES (?, ?, ?, ?);",
            (session_id, prompt, reply, datetime.now().isoformat()),
        )
        cur.execute(
            "INSERT OR IGNORE INTO session_meta (session_id, created_at) VALUES (?, ?)",
            (session_id, datetime.utcnow().isoformat()),
        )
        cur.execute(
            "UPDATE session_meta SET created_at=COALESCE(created_at, ?), updated_at=? WHERE session_id=?",
            (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), session_id),
        )
        conn.commit()
        print("💾 Chat record inserted successfully.")

        # --- 7️⃣ Return JSON response ---
        return {
            "response": reply,
            "context_count": len(rows),
            "session_id": session_id,
        }

    except Exception as e:
        print("❌ Chat endpoint error:", e)
        traceback.print_exc()
        return {"error": str(e)}

    finally:
        try:
            if conn:
                conn.close()
                print("🔒 SQLite connection closed.")
        except Exception as e:
            print("⚠️ Error closing DB:", e)


@app.post("/topic")
def set_topic(new_topic: str = Query(...), user_id: str = "sree"):
    m.add(f"Topic switched to {new_topic}", user_id=user_id,
          agent_id=new_topic, metadata={"type": "system"})
    return {"message": f"✅ Topic set to '{new_topic}'. You haven’t taught me anything yet."}


@app.post("/session")
def new_session(topic: str = "general"):
    sid = start_session(topic)
    return {"session_id": sid, "message": f"🆕 New session started for topic '{topic}'."}



# --- Session tooling endpoints ---

@app.get("/summary")
def summarize_session(session_id: str = Query(..., description="Session to summarize")):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_input, ai_output FROM chat_history WHERE session_id=? ORDER BY id ASC;",
            (session_id,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return {"session_id": session_id, "summary": "No conversation found for this session."}

    joined_transcript = "\n".join(
        f"Teacher: {user}\nStudent: {ai}" for user, ai in rows if user or ai
    )
    prompt = (
        "Provide a concise summary (max 4 sentences) of the following teacher/student exchange. "
        "Focus on what the teacher taught and how the student responded.\n\n"
        f"{joined_transcript}"
    )
    summary_response = ollama.chat(
        model="llama3",
        messages=[{"role": "user", "content": prompt}],
    )
    summary_text = summary_response["message"]["content"].strip()

    m.add(
        summary_text,
        user_id="sree",
        agent_id="general",
        run_id=session_id,
        metadata={"type": "session_summary"},
    )

    return {"session_id": session_id, "summary": summary_text}


@app.get("/search_topic")
def search_topic(query: str = Query(..., description="Keyword to search"), limit: int = 5):
    try:
        results = m.search(query=query, user_id="sree")
    except Exception as search_err:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {search_err}") from search_err

    hits = results.get("results", [])[:limit]
    formatted = [
        {
            "id": item.get("id"),
            "score": item.get("score"),
            "memory": item.get("memory"),
        }
        for item in hits
    ]
    return {"query": query, "results": formatted}


@app.get("/search_history")
def search_all(query: str = Query(...), user_id: str = "sree"):
    res = m.search(query=query, user_id=user_id)
    return {"query": query, "results": res}

@app.get("/inspect_memory")
def inspect_memory(user_id: str = "sree"):
    short = m.search(query="", user_id=user_id, filters={"type": "short_term"})
    long = m.search(query="", user_id=user_id, filters={"type": "long_term"})
    print("\n🧩 Short-term records:")
    for i, s in enumerate(short.get("results", [])):
        print(f"{i+1}. {s.get('memory')[:100]}")

    print("\n📘 Long-term records:")
    for i, l in enumerate(long.get("results", [])):
        print(f"{i+1}. {l.get('memory')[:100]}")

    return {"short_term": short, "long_term": long}
