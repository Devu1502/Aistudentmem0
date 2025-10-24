import React, { useState } from "react";
import axios from "axios";
import { v4 as uuidv4 } from "uuid";

type Memory = {
  id: string;
  text: string;
  metadata?: Record<string, any>;
};

const App = () => {
  const [sessionId, setSessionId] = useState<string>("");
  const [topic, setTopic] = useState<string>("general");
  const [userInput, setUserInput] = useState<string>("");
  const [memories, setMemories] = useState<Memory[]>([]);
  const [log, setLog] = useState<string>("");

  const backend = "http://127.0.0.1:8000";

  // 🧠 Create new chat (resets topic + session)
  const newChat = () => {
    const newSession = uuidv4();
    setSessionId(newSession);
    setTopic("general");
    setMemories([]);
    setLog(`🆕 New chat started (session: ${newSession})`);
  };

  // 🧠 Create new session (keeps topic)
  const newSession = () => {
    const newSession = uuidv4();
    setSessionId(newSession);
    setLog(`🔄 New session started (topic: ${topic}, session: ${newSession})`);
  };

  // 🧠 Change topic
  const newTopic = (t: string) => {
    setTopic(t);
    setLog(`📚 Switched to topic: ${t}`);
  };

  // ➕ Add memory
const addMemory = async () => {
  if (!userInput.trim()) return;
  try {
    const res = await axios.post(
      `${backend}/add`,
      {},
      {
        params: {
          text: userInput,
          session_id: sessionId,
          topic,
          memory_type: "short_term",
        },
      }
    );
    setLog(`✅ Added: ${userInput}`);
    setUserInput("");
    fetchMemories();
  } catch (err) {
    console.error(err);
    setLog("❌ Error adding memory");
  }
};



  // 📜 Fetch all
  const fetchMemories = async () => {
    try {
      const res = await axios.get(`${backend}/all?session_id=${sessionId}&topic=${topic}`);
      setMemories(res.data.memories);
      setLog(`📖 Retrieved ${res.data.memories?.length || 0} memories`);
    } catch {
      setLog("⚠️ Error fetching memories");
    }
  };

  return (
    <div style={{ fontFamily: "sans-serif", padding: "2rem", maxWidth: "800px", margin: "auto" }}>
      <h1>🧠 Mem0 Local UI</h1>
      <p style={{ color: "#555" }}>
        Topic: <b>{topic}</b> | Session: <b>{sessionId || "none"}</b>
      </p>

      <div style={{ marginBottom: "1rem" }}>
        <button onClick={newChat}>➕ New Chat</button>{" "}
        <button onClick={newSession}>🔄 New Session</button>{" "}
        <input
          type="text"
          placeholder="Enter new topic"
          onBlur={(e) => newTopic(e.target.value)}
          style={{ marginLeft: "1rem" }}
        />
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <textarea
          rows={3}
          placeholder="Type a memory..."
          value={userInput}
          onChange={(e) => setUserInput(e.target.value)}
          style={{ width: "100%", padding: "8px" }}
        />
        <button onClick={addMemory}>Add Memory</button>{" "}
        <button onClick={fetchMemories}>Get Memories</button>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <h3>📜 Memories</h3>
        <ul>
          {memories?.map((m: any, i: number) => (
            <li key={i}>
              <b>{m.id || i}</b>: {m.data || m.text}
            </li>
          ))}
        </ul>
      </div>

      <div style={{ marginTop: "2rem" }}>
        <h2>💬 Chat</h2>
        <textarea
          rows={3}
          placeholder="Ask me something..."
          value={userInput}
          onChange={(e) => setUserInput(e.target.value)}
          style={{ width: "100%", padding: "8px" }}
        />
        <button
          onClick={async () => {
            const res = await axios.post(
              `${backend}/chat`,
              {},
              {
                params: {
                  prompt: userInput,
                  session_id: sessionId,
                  topic,
                },
              }
            );
            setLog(`🤖 ${res.data.response}`);
          }}
        >
          Send
        </button>
      </div>

      <p style={{ color: "#007700" }}>{log}</p>
    </div>
  );
};

export default App;
