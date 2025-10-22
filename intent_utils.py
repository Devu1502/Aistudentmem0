import re
import sqlite3
from datetime import datetime
from typing import Optional, Tuple

from memory import LocalMemory

DB_PATH = "/Users/sreekanthgopi/Desktop/Apps/AIStudentMem0/chat_history_memori.db"


def sanitize_reply(reply: str) -> Tuple[str, Optional[str]]:
    """Remove <system_action> tags from the reply and surface the embedded command."""
    action_data = None
    match = re.search(r"<system_action>(.*?)</system_action>", reply, flags=re.DOTALL)
    if match:
        action_data = match.group(1)
        reply = reply.replace(match.group(0), "").strip()
    return reply, action_data


def handle_system_action(action: str, session_id: str, memory: LocalMemory):
    """Execute a hidden system action and return a response + action type."""
    if not action:
        return None, None

    key, *value = action.split("=", 1)
    val = value[0] if value else None

    if key == "topic":
        update_topic(session_id, val or "general")
        return f"✅ Topic switched to {val or 'general'}.", "topic"

    if key == "session":
        sid = start_session(val or "general")
        return f"🆕 New session started ({sid})", "session"

    if key == "reset":
        memory.reset()
        return "🧹 Memory store reset successfully.", "reset"

    return None, None


def update_topic(session_id: str, topic: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "UPDATE session_meta SET topic=? WHERE session_id=?",
        (topic, session_id),
    )
    con.commit()
    con.close()


def start_session(topic: str = "general") -> str:
    sid = datetime.now().strftime("%Y%m%d-%H%M%S")
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO session_meta (session_id, topic, started_at) VALUES (?,?,?)",
        (sid, topic, datetime.now()),
    )
    con.commit()
    con.close()
    return sid


def detect_dev_command(prompt: str):
    """Recognize lightweight developer slash commands."""
    text = prompt.strip().lower()
    if text.startswith("/search_topic"):
        return {"cmd": "search_topic", "arg": " ".join(text.split()[1:])}
    if text.startswith("/reset"):
        return {"cmd": "reset"}
    return None
