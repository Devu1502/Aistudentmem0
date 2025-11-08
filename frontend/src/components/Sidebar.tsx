import React from "react";

import { SessionInfo } from "../hooks/useSessions";

type SidebarProps = {
  sessions: SessionInfo[];
  activeSessionId: string | null;
  refreshing: boolean;
  teachMode: boolean;
  isSending: boolean;
  isUploading: boolean;
  editingSession: string | null;
  newTitle: string;
  onNewChat: () => void;
  onRefresh: () => void;
  onToggleTeachMode: () => void;
  onSelectSession: (sessionId: string) => void;
  onStartRename: (sessionId: string, currentTitle: string) => void;
  onRenameSubmit: (sessionId: string) => void;
  onRenameCancel: () => void;
  onTitleChange: (value: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onClearMongo: () => void;
  onClearQdrant: () => void;
};

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  activeSessionId,
  refreshing,
  teachMode,
  isSending,
  isUploading,
  editingSession,
  newTitle,
  onNewChat,
  onRefresh,
  onToggleTeachMode,
  onSelectSession,
  onStartRename,
  onRenameSubmit,
  onRenameCancel,
  onTitleChange,
  onDeleteSession,
  onClearMongo,
  onClearQdrant,
}) => {
  return (
    <aside className="chat-sidebar">
      <div className="sidebar-header">
        <button className="ghost-button large" onClick={onNewChat}>
          + New Chat
        </button>
        <button className="ghost-button danger" onClick={onClearMongo}>
          Clear MongoDB
        </button>
        <button className="ghost-button danger" onClick={onClearQdrant}>
          Clear Qdrant
        </button>
      </div>

      <div className="sidebar-section">
        <h2>Chats</h2>
        <ul className="session-list">
          {sessions.length === 0 && <li className="empty">No chats yet.</li>}
          {sessions.map((session) => (
            <li
              key={session.session_id}
              className={`session-item ${activeSessionId === session.session_id ? "active" : ""}`}
            >
              {editingSession === session.session_id ? (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    onRenameSubmit(session.session_id);
                  }}
                >
                  <input
                    type="text"
                    value={newTitle}
                    onChange={(event) => onTitleChange(event.target.value)}
                    placeholder="New title"
                    autoFocus
                  />
                  <button type="submit" className="mini-btn">
                    Save
                  </button>
                  <button type="button" className="mini-btn" onClick={onRenameCancel}>
                        X
                  </button>
                </form>
              ) : (
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelectSession(session.session_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectSession(session.session_id);
                    }
                  }}
                >
                  <strong>{session.title || session.preview.slice(0, 30) || "Untitled Chat"}</strong>
                  <p className="preview">{session.preview || "No messages"}</p>
                  <small>
                    {session.last_message_time
                      ? new Date(session.last_message_time).toLocaleString()
                      : ""}
                  </small>
                      <div className="session-actions">
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            onDeleteSession(session.session_id);
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
          onClick={() => {
            void onToggleTeachMode();
          }}
          disabled={isUploading || isSending}
        >
          {teachMode ? "Teach Mode: ON" : "Teach Mode: OFF"}
        </button>
        <p className="sidebar-hint">
          When on, the student stays quiet so you can teach uninterrupted.
        </p>
      </div>
    </aside>
  );
};
