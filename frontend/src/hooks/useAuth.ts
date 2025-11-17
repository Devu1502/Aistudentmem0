import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "../apiConfig";

export type AuthUser = {
  id: string;
  name?: string;
  email: string;
  role?: string;
};

type LoginResult = {
  success: boolean;
  message?: string;
};

export const useAuth = () => {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(true);

  const clearAuth = useCallback(() => {
    localStorage.removeItem("access_token");
    setToken(null);
    setUser(null);
  }, []);

  const fetchProfile = useCallback(
    async (accessToken: string) => {
      try {
        const res = await fetch(`${API_BASE}/auth/me`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!res.ok) {
          throw new Error("Profile fetch failed");
        }
        const data = await res.json();
        if (data?.user) {
          setUser(data.user);
          return true;
        }
      } catch (error) {
        console.error("Auth profile fetch failed", error);
      }
      clearAuth();
      return false;
    },
    [clearAuth]
  );

  useEffect(() => {
    const storedToken = localStorage.getItem("access_token");
    if (!storedToken) {
      setChecking(false);
      return;
    }
    setToken(storedToken);
    fetchProfile(storedToken).finally(() => setChecking(false));
  }, [fetchProfile]);

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      try {
        const res = await fetch(`${API_BASE}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
          const text = await res.text();
          return { success: false, message: text || "Invalid credentials" };
        }
        const data = await res.json();
        if (data?.access_token) {
          localStorage.setItem("access_token", data.access_token);
          setToken(data.access_token);
          await fetchProfile(data.access_token);
          return { success: true };
        }
        return { success: false, message: "Missing token in response." };
      } catch (error) {
        console.error("Login failed", error);
        return { success: false, message: "Unable to login right now." };
      }
    },
    [fetchProfile]
  );

  const logout = useCallback(() => {
    clearAuth();
  }, [clearAuth]);

  return {
    authChecking: checking,
    isAuthenticated: Boolean(token && user),
    user,
    token,
    login,
    logout,
  };
};
