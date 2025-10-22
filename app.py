from fastapi import FastAPI, Query, Request, HTTPException
import uuid
from fastapi.middleware.cors import CORSMiddleware
from intent_utils import detect_dev_command, handle_system_action, sanitize_reply
from memory import LocalMemory, LocalOllamaEmbedder

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

from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv("/Users/sreekanthgopi/Desktop/Apps/AIStudentMem0/.env")

if not os.getenv("OPENAI_API_KEY"):
    raise EnvironmentError("❌ OPENAI_API_KEY not found in environment!")


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
If nothing has been taught yet, say 'You haven’t taught me anything yet.' and also:

Special instructions for topic/session management:
- Always remember the current topic for the session once set.
- If the teacher clearly says to change topic, output:
If the teacher clearly says to change topic or start new session, output a hidden signal in this format:
<system_action>topic=NEW_TOPIC</system_action> or <system_action>session=new</system_action>
If the teacher asks to clear memory or reset, use <system_action>reset</system_action>.
 eg: "Let's switch topics to Quantum Computing." or "Start a new session on Machine Learning."
 response: <system_action>topic=Quantum Computing</system_action> or <system_action>session=new</system_action>
- If the teacher asks to clear memory or reset, use <system_action>reset</system_action>.
- Never output these system actions unless explicitly triggered by the teacher's request.
- if both are asked like new session new topic - do both actions together. eg: user: "Start a new session on Astrophysics and new session."; response: <system_action>session=new;topic=Astrophysics</system_action>

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
- Keep your tone curious, natural, and conversational. Do not treat topic-setting messages as teaching content.

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
        # --- 3️⃣ Fetch chat history for this session ---
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
        try:
            def extract_hits(result):
                return result.get("results", []) if isinstance(result, dict) else (result or [])

            session_hits = extract_hits(
                m.search(query=prompt, user_id="sree", agent_id="general", run_id=session_id)
            )
            combined_hits = session_hits[:]

            if len(combined_hits) < 100:
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

        # --- 4️⃣ Run Agent asynchronously ---
        try:
            print("🤖 Calling OpenAI Agent (async)...")
            user_prompt = (
                f"[Session: {session_id}] [Time: {datetime.now().isoformat()}]\n"
                f"Context:\n{chat_context}\n\nTeacher: {prompt}\nStudent:"
            )
            print(f"🧾 LLM context preview (first 1000 chars):\n{chat_context[:1000]}")

            result = await Runner.run(agent, user_prompt)
            raw_reply = getattr(result, "final_output", "")
            print(f"📝 Raw LLM reply: {raw_reply!r}")
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
