import { useCallback, useState } from "react";
import { API_BASE } from "../apiConfig";

export type SessionInfo = {
  session_id: string;
  last_message_time: string;
  preview: string;
  title?: string;
};

const buildHeaders = (token?: string | null) =>
  token ? { Authorization: `Bearer ${token}` } : undefined;

export const useSessions = (token?: string | null) => {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const fetchSessions = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await fetch(`${API_BASE}/sidebar_sessions`, { headers: buildHeaders(token) });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSessions(Array.isArray(data.sessions) ? data.sessions : []);
      return Array.isArray(data.sessions) ? data.sessions : [];
    } catch (err) {
      console.error("Sidebar fetch failed", err);
      return [] as SessionInfo[];
    } finally {
      setRefreshing(false);
    }
  }, [token]);

  const deleteSession = useCallback(async (sessionId: string) => {
    const res = await fetch(`${API_BASE}/delete_session?session_id=${sessionId}`, {
      method: "DELETE",
      headers: buildHeaders(token),
    });
    if (!res.ok) throw new Error(await res.text());
    await fetchSessions();
  }, [fetchSessions, token]);

  const renameSession = useCallback(async (sessionId: string, newTitle: string) => {
    const res = await fetch(
      `${API_BASE}/rename_session?session_id=${sessionId}&new_name=${encodeURIComponent(newTitle)}`,
      { method: "POST", headers: buildHeaders(token) }
    );
    if (!res.ok) throw new Error(await res.text());
    await fetchSessions();
  }, [fetchSessions, token]);

  return {
    sessions,
    refreshing,
    setSessions,
    fetchSessions,
    deleteSession,
    renameSession,
  };
};
