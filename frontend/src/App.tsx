import React, { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

type MessageRole = "teacher" | "student" | "system";

type Message = {
  id: string;
  role: MessageRole;
  text: string;
  createdAt: string;
};

type CommandDefinition = {
  name: string;
  usage: string;
  description: string;
};

type SessionInfo = {
  session_id: string;
  last_message_time: string;
  preview: string;
  title?: string;
};

const API_BASE = "http://127.0.0.1:8000";

const COMMANDS: CommandDefinition[] = [
  {
    name: "topic",
    usage: "/topic <new_topic>",
    description: "Switch the current lesson topic",
  },
  {
    name: "session",
    usage: "/session new",
    description: "Start a brand-new session",
  },
  {
    name: "summary",
    usage: "/summary",
    description: "Summarize the active session",
  },
  {
    name: "search_topic",
    usage: "/search_topic <keywords>",
    description: "Search every stored memory for keywords",
  },
  {
    name: "all",
    usage: "/all",
    description: "List every stored memory entry",
  },
  {
    name: "reset",
    usage: "/reset",
    description: "Clear the entire local memory store",
  },
  {
    name: "help",
    usage: "/help",
    description: "Display the command reference",
  },
  {
    name: "search",
    usage: "/search <keywords>",
    description: "Legacy search on the active filters",
  },
];

const createMessage = (role: MessageRole, text: string): Message => ({
  id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
  role,
  text,
  createdAt: new Date().toISOString(),
});

const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

const ROLE_META: Record<MessageRole, { label: string; initial: string }> = {
  teacher: { label: "Teacher", initial: "T" },
  student: { label: "Student", initial: "S" },
  system: { label: "System", initial: "ℹ" },
};

export default function ChatApp() {
  const [messages, setMessages] = useState<Message[]>(() => [
    createMessage("system", "Welcome! Let’s start when you’re ready to teach."),
  ]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [teachMode, setTeachMode] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [editingSession, setEditingSession] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const bottomRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const pushSystemMessage = (text: string) => {
    setMessages((prev) => [...prev, createMessage("system", text)]);
  };

  const fetchTeachMode = async () => {
    try {
      const res = await fetch(`${API_BASE}/teach_mode`);
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      setTeachMode(Boolean(data?.teach_mode));
    } catch (error) {
      console.error("Failed to load Teach Mode state", error);
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending]);

  useEffect(() => {
    fetchTeachMode();
    fetchSessions(true);
  }, []);

  const filteredCommands = useMemo(() => {
    if (!showSuggestions) {
      return [];
    }
    const token = commandQuery.trim();
    if (!token) {
      return COMMANDS;
    }
    return COMMANDS.filter((cmd) =>
      cmd.name.toLowerCase().includes(token) || cmd.usage.toLowerCase().includes(token)
    );
  }, [commandQuery, showSuggestions]);

  const closeCommandPalette = () => {
    setShowSuggestions(false);
    setCommandQuery("");
  };

  const updateTeachMode = async (enabled: boolean) => {
    try {
      const res = await fetch(`${API_BASE}/teach_mode?enabled=${enabled}`, { method: "POST" });
      if (!res.ok) {
        const text = await res.text();
        pushSystemMessage(`❌ Teach Mode update failed: ${text || res.statusText}`);
        return;
      }
      const data = await res.json();
      const state = Boolean(data?.teach_mode);
      setTeachMode(state);
      pushSystemMessage(`Teach Mode ${state ? "ON" : "OFF"}.`);
    } catch (error) {
      console.error("Failed to update Teach Mode", error);
      pushSystemMessage("⚠️ Could not reach the Teach Mode endpoint.");
    }
  };

  const handleToggleTeachMode = async () => {
    await updateTeachMode(!teachMode);
  };

  const handleFileInputChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) {
      return;
    }

    const files = Array.from(fileList);
    if (files.length > 5) {
      pushSystemMessage("Please upload up to 5 files at a time.");
      event.target.value = "";
      return;
    }

    setIsUploading(true);
    try {
      const formData = new FormData();
      files.forEach((file) => formData.append("files", file));

      const response = await fetch(`${API_BASE}/documents/upload`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorText = await response.text();
        pushSystemMessage(`❌ Upload failed: ${errorText || response.statusText}`);
        return;
      }

      const data = await response.json();
      const uploaded = Array.isArray(data.uploaded) ? data.uploaded : [];
      const errors = Array.isArray(data.errors) ? data.errors : [];

      if (uploaded.length > 0) {
        const names = uploaded.map((item: any) => item?.filename || "document").join(", ");
        pushSystemMessage(`📄 Uploaded ${uploaded.length} document(s): ${names}.`);
      }

      errors.forEach((err: any) => {
        if (err?.filename && err?.error) {
          pushSystemMessage(`⚠️ ${err.filename}: ${err.error}`);
        }
      });
    } catch (error) {
      console.error("Upload failed", error);
      pushSystemMessage("⚠️ Could not upload documents. Please try again.");
    } finally {
      setIsUploading(false);
      event.target.value = "";
    }
  };

  const fetchSessions = async (autoLoad: boolean = false) => {
    setRefreshing(true);
    try {
      const res = await fetch(`${API_BASE}/sidebar_sessions`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const list: SessionInfo[] = Array.isArray(data.sessions) ? data.sessions : [];
      setSessions(list);
      if (autoLoad && list.length > 0) {
        await handleSelectSession(list[0].session_id);
      }
    } catch (err) {
      console.error("Sidebar fetch failed", err);
    } finally {
      setRefreshing(false);
    }
  };

  const handleDeleteSession = async (sessionIdToDelete: string) => {
    if (!window.confirm("Delete this chat permanently?")) return;
    try {
      const res = await fetch(`${API_BASE}/delete_session?session_id=${sessionIdToDelete}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      if (sessionId === sessionIdToDelete) {
        setSessionId(null);
        setMessages([
          createMessage(
            "system",
            "Session deleted. Start a new chat or pick another conversation from the list."
          ),
        ]);
      }
      await fetchSessions(sessionId === sessionIdToDelete);
    } catch (err) {
      console.error("Delete failed", err);
      pushSystemMessage("⚠️ Failed to delete session.");
    }
  };

  const handleRenameSession = async (sessionId: string) => {
    if (!newTitle.trim()) {
      pushSystemMessage("Provide a new title before saving.");
      return;
    }
    try {
      const res = await fetch(
        `${API_BASE}/rename_session?session_id=${sessionId}&new_name=${encodeURIComponent(newTitle.trim())}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(await res.text());
      setEditingSession(null);
      setNewTitle("");
      await fetchSessions();
    } catch (err) {
      console.error("Rename failed", err);
      pushSystemMessage("⚠️ Failed to rename session.");
    }
  };

  const handleSelectSession = async (sessionId: string) => {
    try {
      const res = await fetch(`${API_BASE}/session_messages?session_id=${sessionId}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSessionId(sessionId);
      setMessages(
        (data.messages || []).map((m: any) => ({
          id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          role: m.role === "assistant" ? "student" : "teacher",
          text: m.content,
          createdAt: m.timestamp || new Date().toISOString(),
        }))
      );
    } catch (err) {
      console.error("Session load failed", err);
      pushSystemMessage("⚠️ Failed to load session.");
    }
  };

  const handleInputChange = (value: string) => {
    setInput(value);
    if (value.startsWith("/")) {
      const afterSlash = value.slice(1).toLowerCase();
      const [firstToken = ""] = afterSlash.split(/\s+/);
      setShowSuggestions(true);
      setCommandQuery(firstToken);
    } else {
      closeCommandPalette();
    }
  };

  const handleNewChat = () => {
    setMessages([
      createMessage(
        "system",
        "New chat started. Use /topic <subject> when you're ready to begin teaching."
      ),
    ]);
    setSessionId(null);
    setInput("");
    closeCommandPalette();
  };

  const processInput = async (rawInput: string) => {
    const trimmed = rawInput.trim();
    if (!trimmed) return;

    setInput("");

    if (trimmed.startsWith("/")) {
      closeCommandPalette();
      await handleCommand(trimmed);
      return;
    }

    closeCommandPalette();
    await sendPrompt(trimmed);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await processInput(input);
  };

  const sendPrompt = async (prompt: string) => {
    const teacherMessage = createMessage("teacher", prompt);
    setMessages((prev) => [...prev, teacherMessage]);
    setIsSending(true);

    try {
      const url = new URL(`${API_BASE}/chat`);
      url.searchParams.set("prompt", prompt);
      if (sessionId) {
        url.searchParams.set("session_id", sessionId);
      }

      const response = await fetch(url.toString(), { method: "POST" });
      if (!response.ok) {
        const errorText = await response.text();
        setMessages((prev) => [
          ...prev,
          createMessage("system", `❌ Server error: ${errorText || response.statusText}`),
        ]);
        return;
      }

      const data = await response.json();
      setSessionId(data.session_id ?? sessionId);

      const rawResponse = typeof data.response === "string" ? data.response : "";
      const trimmedResponse = rawResponse.trim();
      const assistantReply =
        trimmedResponse.length > 0
          ? trimmedResponse
          : teachMode
          ? ""
          : "I did not receive a response from the model.";

      setMessages((prev) => [...prev, createMessage("student", assistantReply)]);
      fetchSessions();
    } catch (error) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        createMessage("system", "⚠️ Connection error. Confirm the FastAPI server is running."),
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const handleCommand = async (rawCommand: string) => {
    const stripped = rawCommand.slice(1).trim();
    const commandMessage = createMessage("teacher", rawCommand);

    if (!stripped) {
      setMessages((prev) => [
        ...prev,
        commandMessage,
        createMessage("system", "Type /help to see the available commands."),
      ]);
      return;
    }

    const [commandToken, ...args] = stripped.split(/\s+/);
    const normalized = commandToken.toLowerCase();

    const appendSystem = (...systemTexts: string[]) => {
      setMessages((prev) => [
        ...prev,
        commandMessage,
        ...systemTexts.map((text) => createMessage("system", text)),
      ]);
    };

    if (normalized === "topic") {
      const topic = args.join(" ").trim();
      if (!topic) {
        appendSystem("Usage: /topic <new_topic>");
        return;
      }
      try {
        const url = new URL(`${API_BASE}/topic`);
        url.searchParams.set("new_topic", topic);
        const res = await fetch(url.toString(), { method: "POST" });
        if (!res.ok) {
          const text = await res.text();
          appendSystem(`❌ Topic update failed: ${text || res.statusText}`);
          return;
        }
        const data = await res.json();
        appendSystem(data.message ?? `✅ Topic set to '${topic}'.`);
      } catch (error) {
        console.error(error);
        appendSystem("⚠️ Could not reach the topic endpoint.");
      }
      return;
    }

    if (normalized === "session") {
      const sub = (args[0] || "").toLowerCase();
      if (sub === "new") {
        try {
          const res = await fetch(`${API_BASE}/session`, { method: "POST" });
          if (!res.ok) {
            const text = await res.text();
            appendSystem(`❌ Session start failed: ${text || res.statusText}`);
            return;
          }
          const data = await res.json();
          handleNewChat();
          setSessionId(data.session_id ?? null);
          setMessages((prev) => [
            ...prev,
            commandMessage,
            createMessage("system", data.message ?? "🆕 New session started."),
          ]);
        } catch (error) {
          console.error(error);
          appendSystem("⚠️ Could not start a new session.");
        }
      } else {
        appendSystem("Usage: /session new");
      }
      return;
    }

    if (normalized === "summary") {
      if (!sessionId) {
        appendSystem("No active session. Use /session new to begin.");
        return;
      }
      try {
        const url = new URL(`${API_BASE}/summary`);
        url.searchParams.set("session_id", sessionId);
        const res = await fetch(url.toString());
        if (!res.ok) {
          const text = await res.text();
          appendSystem(`❌ Summary failed: ${text || res.statusText}`);
          return;
        }
        const data = await res.json();
        const summary = typeof data.summary === "string" ? data.summary : JSON.stringify(data.summary);
        appendSystem(`📘 Session summary:\n\n${summary}`);
      } catch (error) {
        console.error(error);
        appendSystem("⚠️ Could not retrieve the summary.");
      }
      return;
    }

    if (normalized === "search_topic") {
      const query = args.join(" ").trim();
      if (!query) {
        appendSystem("Usage: /search_topic <keywords>");
        return;
      }
      try {
        const url = new URL(`${API_BASE}/search_topic`);
        url.searchParams.set("query", query);
        const res = await fetch(url.toString());
        if (!res.ok) {
          const text = await res.text();
          appendSystem(`❌ Topic search failed: ${text || res.statusText}`);
          return;
        }
        const data = await res.json();
        const hits = Array.isArray(data.results) ? data.results : [];
        if (hits.length === 0) {
          appendSystem(`No memories matched “${query}”.`);
          return;
        }
        const formatted = hits
          .map(
            (item: any, index: number) =>
              `${index + 1}. ${item?.memory ?? "—"}\n   score: ${item?.score?.toFixed?.(3) ?? "?"}`
          )
          .join("\n\n");
        appendSystem(`🔍 Memories mentioning “${query}”:\n\n${formatted}`);
      } catch (error) {
        console.error(error);
        appendSystem("⚠️ Could not reach the search endpoint.");
      }
      return;
    }

    if (normalized === "search") {
      const query = args.join(" ").trim();
      if (!query) {
        appendSystem("Usage: /search <keywords>");
        return;
      }
      try {
        const url = new URL(`${API_BASE}/search`);
        url.searchParams.set("query", query);
        const res = await fetch(url.toString());
        if (!res.ok) {
          const text = await res.text();
          appendSystem(`❌ Search failed: ${text || res.statusText}`);
          return;
        }
        const data = await res.json();
        const hits = Array.isArray(data.results?.results)
          ? data.results.results
          : Array.isArray(data.results)
          ? data.results
          : [];
        if (hits.length === 0) {
          appendSystem(`No memories matched “${query}”.`);
          return;
        }
        const formatted = hits
          .map((item: any, index: number) => {
            const memoryText = item?.memory ?? item?.value ?? JSON.stringify(item);
            return `${index + 1}. ${memoryText}`;
          })
          .join("\n\n");
        appendSystem(`🔍 Search results for “${query}”:\n\n${formatted}`);
      } catch (error) {
        console.error(error);
        appendSystem("⚠️ Could not reach the search API.");
      }
      return;
    }

    if (normalized === "all") {
      try {
        const res = await fetch(`${API_BASE}/all`);
        if (!res.ok) {
          const text = await res.text();
          appendSystem(`❌ Fetch failed: ${text || res.statusText}`);
          return;
        }
        const data = await res.json();
        const memories = Array.isArray(data.memories) ? data.memories : [];
        if (memories.length === 0) {
          appendSystem("No stored memories yet.");
          return;
        }
        const formatted = memories
          .map((item: any, index: number) => {
            const meta = item?.metadata?.type ? ` (${item.metadata.type})` : "";
            const base = item?.memory ?? item?.value ?? JSON.stringify(item);
            return `${index + 1}. ${base}${meta}`;
          })
          .join("\n\n");
        appendSystem(`🗂️ Complete memory listing:\n\n${formatted}`);
      } catch (error) {
        console.error(error);
        appendSystem("⚠️ Could not fetch stored memories.");
      }
      return;
    }

    if (normalized === "reset") {
      try {
        const res = await fetch(`${API_BASE}/reset`, { method: "POST" });
        if (!res.ok) {
          const text = await res.text();
          appendSystem(`❌ Reset failed: ${text || res.statusText}`);
          return;
        }
        const data = await res.json();
        appendSystem(data?.message ?? "Memory reset complete.");
      } catch (error) {
        console.error(error);
        appendSystem("⚠️ Could not reach the reset endpoint.");
      }
      return;
    }

    if (normalized === "help") {
      const helpText = COMMANDS.map((cmd) => `${cmd.usage} — ${cmd.description}`).join("\n");
      appendSystem(helpText);
      return;
    }

    appendSystem(`Unknown command “/${normalized}”. Try /help.`);
  };

  const applyCommandTemplate = (command: CommandDefinition) => {
    const template = command.usage.endsWith(" ") ? command.usage : `${command.usage} `;
    setInput(template);
    setCommandQuery("");
    setShowSuggestions(false);
  };

  return (
    <div className="chat-app">
      <div className="chat-shell">
        <aside className="chat-sidebar">
          <div className="sidebar-header">
            <button className="ghost-button large" onClick={handleNewChat}>
              + New Chat
            </button>
            <button className="ghost-button" onClick={() => fetchSessions()} disabled={refreshing}>
              {refreshing ? "Refreshing…" : "↻ Refresh"}
            </button>
          </div>

          <div className="sidebar-section">
            <h2>Chats</h2>
            <ul className="session-list">
              {sessions.length === 0 && <li className="empty">No chats yet.</li>}
              {sessions.map((s) => (
                <li
                  key={s.session_id}
                  className={`session-item ${sessionId === s.session_id ? "active" : ""}`}
                >
                  {editingSession === s.session_id ? (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        handleRenameSession(s.session_id);
                      }}
                    >
                      <input
                        type="text"
                        value={newTitle}
                        onChange={(e) => setNewTitle(e.target.value)}
                        placeholder="New title"
                        autoFocus
                      />
                      <button type="submit" className="mini-btn">
                        Save
                      </button>
                      <button
                        type="button"
                        className="mini-btn"
                        onClick={() => {
                          setEditingSession(null);
                          setNewTitle("");
                        }}
                      >
                        ✖
                      </button>
                    </form>
                  ) : (
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => handleSelectSession(s.session_id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleSelectSession(s.session_id);
                        }
                      }}
                    >
                      <strong>{s.title || s.preview.slice(0, 30) || "Untitled Chat"}</strong>
                      <p className="preview">{s.preview || "No messages"}</p>
                      <small>
                        {s.last_message_time
                          ? new Date(s.last_message_time).toLocaleString()
                          : ""}
                      </small>
                      <div className="session-actions">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingSession(s.session_id);
                            setNewTitle(s.title || s.preview || "");
                          }}
                        >
                          ✏️
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteSession(s.session_id);
                          }}
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div className="sidebar-section">
            <h2>Teach Mode</h2>
            <button
              type="button"
              className={`ghost-button teach-toggle ${teachMode ? "active" : ""}`}
              onClick={handleToggleTeachMode}
              disabled={isUploading || isSending}
            >
              {teachMode ? "Teach Mode: ON" : "Teach Mode: OFF"}
            </button>
            <p className="sidebar-hint">
              When on, the student stays quiet so you can teach uninterrupted.
            </p>
          </div>
        </aside>

        <main className="chat-main">
          <header className="chat-header">
            <div>
              <h2 className="chat-header-title">AI Student Mentor</h2>
              <p className="chat-header-subtitle">
                Guide the learner and the assistant will respond with grounded context.
              </p>
            </div>
            <span className={`status-badge ${isSending ? "typing" : "idle"}`}>
              {isSending ? "Generating…" : "Idle"}
            </span>
          </header>

          <section className="message-list">
            {messages.map((message) => (
              <article
                key={message.id}
                className={`message-row ${message.role}`}
                aria-label={`${ROLE_META[message.role].label} message`}
              >
                <div className={`message-avatar ${message.role}`}>
                  {ROLE_META[message.role].initial}
                </div>
                <div className={`message-bubble ${message.role}`}>
                  <div className="message-meta">
                    <span className="role">{ROLE_META[message.role].label}</span>
                    <span className="time">{formatTime(message.createdAt)}</span>
                  </div>
                  <div className="message-text">{message.text}</div>
                </div>
              </article>
            ))}

            {isSending && (
              <article className="message-row student typing" aria-live="polite">
                <div className="message-avatar student">S</div>
                <div className="message-bubble student">
                  <div className="message-meta">
                    <span className="role">Student</span>
                    <span className="time">…</span>
                  </div>
                  <div className="typing-indicator">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </article>
            )}
            <div ref={bottomRef} />
          </section>

          <form className="chat-input" onSubmit={handleSubmit}>
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: "none" }}
              multiple
              accept=".pdf,.ppt,.pptx,.doc,.docx,.xls,.xlsx,.md,.txt,.png,.jpg,.jpeg,.heic,.bmp,.csv,.tsv"
              onChange={handleFileInputChange}
            />
            <div className="chat-textarea-wrapper">
              <textarea
                className="chat-textarea"
                placeholder="Enter your message."
                value={input}
                disabled={isSending}
                onChange={(event) => handleInputChange(event.target.value)}
                onKeyDown={async (event) => {
                  if (event.key === "Escape" && showSuggestions) {
                    event.preventDefault();
                    closeCommandPalette();
                    return;
                  }
                  if (event.key === "Tab" && showSuggestions && filteredCommands.length > 0) {
                    event.preventDefault();
                    applyCommandTemplate(filteredCommands[0]);
                    return;
                  }
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    await processInput(input);
                  }
                }}
                rows={Math.min(6, input.split("\n").length + 1)}
              />

              {/* {showSuggestions && filteredCommands.length > 0 && (
                <div className="command-suggestions">
                  {filteredCommands.map((cmd) => (
                    <button
                      key={cmd.name}
                      type="button"
                      className="command-suggestion"
                      onMouseDown={(event) => {
                        event.preventDefault();
                        applyCommandTemplate(cmd);
                      }}
                    >
                      <strong>{cmd.usage}</strong>
                      <span>{cmd.description}</span>
                    </button>
                  ))}
                </div>
              )} */}
            </div>

            <div className="chat-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading || isSending}
              >
                {isUploading ? "Uploading…" : "Upload Docs"}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setInput((prev) => `${prev}\n`)}
                disabled={isSending}
              >
                New line
              </button>
              <button type="submit" className="primary-button" disabled={isSending}>
                {isSending ? "Sending…" : "Send"}
              </button>
            </div>
          </form>
        </main>
      </div>
    </div>
  );
}
