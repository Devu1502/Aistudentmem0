import { useCallback, useState } from "react";
import { API_BASE } from "../apiConfig";

const buildHeaders = (token?: string | null) =>
  token ? { Authorization: `Bearer ${token}` } : undefined;

export const useTeachMode = (token?: string | null) => {
  const [teachMode, setTeachMode] = useState(false);
  const [loading, setLoading] = useState(false);

  const refreshTeachMode = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/teach_mode`, { headers: buildHeaders(token) });
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      setTeachMode(Boolean(data?.teach_mode));
    } catch (error) {
      console.error("Failed to load Teach Mode state", error);
    }
  }, [token]);

  const toggleTeachMode = useCallback(
    async (enabled: boolean) => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/teach_mode?enabled=${enabled}`, {
          method: "POST",
          headers: buildHeaders(token),
        });
        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || res.statusText);
        }
        const data = await res.json();
        setTeachMode(Boolean(data?.teach_mode));
        return true;
      } catch (error) {
        console.error("Failed to update Teach Mode", error);
        return false;
      } finally {
        setLoading(false);
      }
    },
    [token]
  );

  return {
    teachMode,
    loading,
    refreshTeachMode,
    toggleTeachMode,
  };
};
