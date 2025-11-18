// Frontend entry point that wires up chat, sessions, and audio helpers.
import React, { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import "./App.css";

import { Sidebar } from "./components/Sidebar";
import { AuthShell } from "./components/AuthShell";
import { LoginForm } from "./components/LoginForm";
import { SignupForm, SignupFormValues } from "./components/SignupForm";
import TermsPage from "./pages/TermsPage";
import { useTeachMode } from "./hooks/useTeachMode";
import { useSessions } from "./hooks/useSessions";
import { useAuth } from "./hooks/useAuth";
import { API_BASE } from "./apiConfig";

type MessageRole = "teacher" | "student" | "system";
type TeachStatus = "idle" | "learning" | "learned";

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

// Speech endpoints exposed by the FastAPI backend.
const STT_URL = `${API_BASE}/stt`;
const TTS_URL = `${API_BASE}/tts`;

// Handy slash commands surfaced in the command palette.
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
  {
    name: "vectorsearch",
    usage: "/vectorsearch <query>",
    description: "Combined semantic search across chat memory and documents",
  },
  {
    name: "documentvectorsearch",
    usage: "/documentvectorsearch <query>",
    description: "Semantic search only within uploaded documents",
  },
];

// Helper to stamp messages with ids/timestamps before rendering.
const createMessage = (role: MessageRole, text: string): Message => ({
  id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
  role,
  text,
  createdAt: new Date().toISOString(),
});

// Format timestamps for message metadata display.
const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

// Ensure signup requests accept the currently published terms.
const TERMS_VERSION = "v1";

export default function ChatApp() {
  // Core chat state covers message log, auth, sessions, and audio flows.
  const [messages, setMessages] = useState<Message[]>(() => [
    createMessage("system", "Welcome! Let's start when you're ready to teach."),
  ]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const { authChecking, isAuthenticated, user, token, login, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const pathNormalized = location.pathname.replace(/\/+$/, "") || "/";
  const { teachMode, refreshTeachMode, toggleTeachMode } = useTeachMode(token);
  const { sessions, refreshing, fetchSessions, deleteSession, renameSession } = useSessions(token);
  const [isUploading, setIsUploading] = useState(false);
  const [editingSession, setEditingSession] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [teachStatus, setTeachStatus] = useState<TeachStatus>("idle");
  // Compute display labels/initials for the teacher and AI buddy.
  const studentName = useMemo(() => {
    const trimmed = user?.name?.trim();
    return trimmed && trimmed.length > 0 ? trimmed : "You";
  }, [user?.name]);
  const studentInitial = useMemo(() => {
    return studentName.charAt(0).toUpperCase();
  }, [studentName]);
  const roleMeta = useMemo<Record<MessageRole, { label: string; initial: string }>>(
    () => ({
      teacher: { label: studentName, initial: studentInitial },
      student: { label: "AI Buddy", initial: "A" },
      system: { label: "System", initial: "S" },
    }),
    [studentInitial, studentName]
  );

  // Wrap fetch so every request automatically carries the auth token.
  const authedFetch = useCallback(
    (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers || {});
      if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      }
      return fetch(input, { ...init, headers });
    },
    [token]
  );

  // Create an account and immediately log the user in.
  const handleSignup = useCallback(
    async (values: SignupFormValues) => {
      try {
        const payload = {
          name: values.name.trim(),
          email: values.email.trim().toLowerCase(),
          password: values.password,
          password_confirm: values.passwordConfirm,
          accept_terms: true,
          terms_version: TERMS_VERSION,
        };
        const res = await fetch(`${API_BASE}/auth/signup`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const text = await res.text();
          return { success: false, message: text || "Unable to create account." };
        }
        const loginResult = await login(values.email, values.password);
        if (!loginResult.success) {
          return {
            success: false,
            message: loginResult.message ?? "Account created but auto-login failed. Please sign in manually.",
          };
        }
        return { success: true };
      } catch (error) {
        console.error("Signup failed", error);
        return { success: false, message: "Unable to create an account right now." };
      }
    },
    [login]
  );

  // Track DOM nodes and browser primitives needed for scrolling/audio.
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const initialisedRef = useRef(false);
  const teachStatusTimeoutRef = useRef<number | null>(null);

  // Append helper text from local actions or command responses.
  const pushSystemMessage = useCallback((text: string) => {
    setMessages((prev) => [...prev, createMessage("system", text)]);
  }, []);

  // Load a saved conversation and hydrate the chat panel.
  const handleSelectSession = useCallback(
    async (selectedSessionId: string) => {
      try {
        const res = await authedFetch(`${API_BASE}/session_messages?session_id=${selectedSessionId}`);
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        setSessionId(selectedSessionId);
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
        pushSystemMessage("Failed to load session.");
      }
    },
    [authedFetch, pushSystemMessage]
  );

  // Scroll to the bottom whenever messages change.
  // After login, fetch Teach Mode status and initial sessions.
  // Reset initialization flags when signing out.
  // Clear pending teach mode timers on unmount.
  // When Teach Mode toggles, refresh the status indicator.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending]);

  useEffect(() => {
    if (!isAuthenticated || !token) {
      return;
    }
    if (initialisedRef.current) {
      return;
    }
    initialisedRef.current = true;

    const initialise = async () => {
      await refreshTeachMode();
      const list = await fetchSessions();
      if (!sessionId && list.length > 0) {
        await handleSelectSession(list[0].session_id);
      }
    };

    initialise();
  }, [fetchSessions, handleSelectSession, isAuthenticated, refreshTeachMode, sessionId, token]);

  useEffect(() => {
    if (!isAuthenticated) {
      initialisedRef.current = false;
    }
  }, [isAuthenticated]);

  // Filter slash commands when the palette is visible.
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

  // Remember the most recent assistant reply for playback options.
  const latestAssistantMessage = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.role === "student") {
        return message;
      }
    }
    return null;
  }, [messages]);

  const hasAssistantReply = Boolean(latestAssistantMessage);

  // Utility that hides and resets the autocomplete overlay.
  const closeCommandPalette = () => {
    setShowSuggestions(false);
    setCommandQuery("");
  };

  // Toggle teach mode and show feedback to the user.
  const handleToggleTeachMode = useCallback(async () => {
    const success = await toggleTeachMode(!teachMode);
    if (success) {
      pushSystemMessage(`Teach Mode ${!teachMode ? "ON" : "OFF"}.`);
    } else {
      pushSystemMessage("Could not reach the Teach Mode endpoint.");
    }
  }, [teachMode, toggleTeachMode, pushSystemMessage]);

  // Upload supporting documents to the backend ingestion route.
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

      const response = await authedFetch(`${API_BASE}/documents/upload`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorText = await response.text();
        pushSystemMessage(`Upload failed: ${errorText || response.statusText}`);
        return;
      }

      const data = await response.json();
      const uploaded = Array.isArray(data.uploaded) ? data.uploaded : [];
      const errors = Array.isArray(data.errors) ? data.errors : [];

      if (uploaded.length > 0) {
        const names = uploaded.map((item: any) => item?.filename || "document").join(", ");
        pushSystemMessage(`Uploaded ${uploaded.length} document(s): ${names}.`);
      }

      errors.forEach((err: any) => {
        if (err?.filename && err?.error) {
          pushSystemMessage(`${err.filename}: ${err.error}`);
        }
      });
    } catch (error) {
      console.error("Upload failed", error);
      pushSystemMessage("Could not upload documents. Please try again.");
    } finally {
      setIsUploading(false);
      event.target.value = "";
    }
  };

  // Remove a chat thread and fall back to a fresh system message.
  const handleDeleteSession = useCallback(async (sessionIdToDelete: string) => {
    if (!window.confirm("Delete this chat permanently?")) return;
    try {
      await deleteSession(sessionIdToDelete);
      if (sessionId === sessionIdToDelete) {
        setSessionId(null);
        setMessages([
          createMessage(
            "system",
            "Session deleted. Start a new chat or pick another conversation from the list."
          ),
        ]);
      }
    } catch (err) {
      console.error("Delete failed", err);
      pushSystemMessage("Failed to delete session.");
    }
  }, [deleteSession, pushSystemMessage, sessionId]);

  // Persist the edited title then clear edit state.
  const handleRenameSession = useCallback(async (sessionId: string) => {
    if (!newTitle.trim()) {
      pushSystemMessage("Provide a new title before saving.");
      return;
    }
    try {
      await renameSession(sessionId, newTitle.trim());
      setEditingSession(null);
      setNewTitle("");
    } catch (err) {
      console.error("Rename failed", err);
        pushSystemMessage("Failed to rename session.");
    }
  }, [newTitle, pushSystemMessage, renameSession]);

  // Initialize inline session rename mode.
  const handleStartRename = useCallback((sessionId: string, currentTitle: string) => {
    setEditingSession(sessionId);
    setNewTitle(currentTitle);
  }, []);

  // Exit rename mode without saving.
  const handleRenameCancel = useCallback(() => {
    setEditingSession(null);
    setNewTitle("");
  }, []);

  // Capture microphone audio and send it to the STT endpoint.
  const startRecording = async () => {
    if (isRecording || isTranscribing) {
      return;
    }

    try {
      setAudioError(null);
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("Microphone not supported in this browser");
      }
      if (typeof MediaRecorder === "undefined") {
        throw new Error("MediaRecorder API unavailable");
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      const chunks: Blob[] = [];

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      recorder.onstop = async () => {
        setIsRecording(false);
        setIsTranscribing(true);
        recorderRef.current = null;
        recorder.stream.getTracks().forEach((track) => track.stop());

        const audioBlob = new Blob(chunks, { type: "audio/webm" });
        if (audioBlob.size === 0) {
          setIsTranscribing(false);
          setAudioError("No audio captured");
          return;
        }

        const formData = new FormData();
        formData.append("file", audioBlob, "speech.webm");

        try {
          const response = await fetch(STT_URL, { method: "POST", body: formData });
          if (!response.ok) {
            throw new Error(`Transcription failed (${response.status})`);
          }
          const data = (await response.json()) as { text?: string };
          setInput(data.text ?? "");
          setAudioError(null);
        } catch (err) {
          setAudioError(err instanceof Error ? err.message : "Unable to transcribe audio");
        } finally {
          setIsTranscribing(false);
        }
      };

      recorder.start();
      recorderRef.current = recorder;
      setIsRecording(true);
    } catch (err) {
      setIsRecording(false);
      setAudioError(err instanceof Error ? err.message : "Microphone permission denied");
    }
  };

  // Stop the recording session and clean up MediaRecorder refs.
  const stopRecording = () => {
    const recorder = recorderRef.current;
    if (!recorder) {
      return;
    }
    recorder.stop();
    setIsRecording(false);
    recorderRef.current = null;
  };

  // Convert the latest assistant message into audio playback.
  const playLatestReply = async () => {
    if (isPlaying || isSending || isTranscribing) {
      return;
    }
    if (!latestAssistantMessage) {
      setAudioError("No assistant reply available");
      return;
    }

    setAudioError(null);
    setIsPlaying(true);

    let audioUrl: string | null = null;
    let audio: HTMLAudioElement | null = null;

    try {
      const speechResponse = await fetch(TTS_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: latestAssistantMessage.text }),
      });

      if (!speechResponse.ok) {
        throw new Error(`Speech playback failed (${speechResponse.status})`);
      }

      const audioBlob = await speechResponse.blob();
      audioUrl = URL.createObjectURL(audioBlob);
      audio = new Audio(audioUrl);

      audio.onended = () => {
        setIsPlaying(false);
        if (audioUrl) {
          URL.revokeObjectURL(audioUrl);
        }
      };
      audio.onerror = () => {
        setIsPlaying(false);
        if (audioUrl) {
          URL.revokeObjectURL(audioUrl);
        }
        setAudioError("Unable to play audio");
      };

      await audio.play();
    } catch (err) {
      setIsPlaying(false);
      if (audio) {
        audio.pause();
      }
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
      setAudioError(err instanceof Error ? err.message : "Playback error");
    }
  };

  useEffect(() => {
    return () => {
      if (teachStatusTimeoutRef.current) {
        clearTimeout(teachStatusTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!teachMode && teachStatus !== "idle") {
      setTeachStatus("idle");
      if (teachStatusTimeoutRef.current) {
        clearTimeout(teachStatusTimeoutRef.current);
        teachStatusTimeoutRef.current = null;
      }
    }
  }, [teachMode, teachStatus]);

  // Track textarea changes and trigger the command palette when needed.
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

  // Reset the chat panel to an empty state.
  const handleNewChat = () => {
    setMessages([createMessage("system", "Hello! I am ready to learn.")]);
    setSessionId(null);
    setInput("");
    closeCommandPalette();
  };

  // Decide whether input is a slash command or a prompt for the agent.
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

  // Form submit handler that pipes text into processInput.
  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await processInput(input);
  };

  // Send the teacher prompt to the backend and handle teach-mode UX.
  const sendPrompt = async (prompt: string) => {
    const teachModeDuringSend = teachMode;
    if (teachModeDuringSend) {
      if (teachStatusTimeoutRef.current) {
        clearTimeout(teachStatusTimeoutRef.current);
        teachStatusTimeoutRef.current = null;
      }
      setTeachStatus("learning");
    } else if (teachStatus !== "idle") {
      setTeachStatus("idle");
    }

    const teacherMessage = createMessage("teacher", prompt);
    setMessages((prev) => [...prev, teacherMessage]);
    setIsSending(true);

    let silentResponse = false;

    try {
      const url = new URL(`${API_BASE}/chat`);
      url.searchParams.set("prompt", prompt);
      if (sessionId) {
        url.searchParams.set("session_id", sessionId);
      }

      const response = await authedFetch(url.toString(), { method: "POST" });
      if (!response.ok) {
        const errorText = await response.text();
        setMessages((prev) => [
          ...prev,
          createMessage("system", `Server error: ${errorText || response.statusText}`),
        ]);
        return;
      }

      const data = await response.json();
      setSessionId(data.session_id ?? sessionId);

      silentResponse = Boolean(data.silent);
      const rawResponse = typeof data.response === "string" ? data.response : "";
      const trimmedResponse = rawResponse.trim();
      const assistantReply =
        trimmedResponse.length > 0 ? trimmedResponse : "I did not receive a response from the model.";

      if (!silentResponse) {
        setMessages((prev) => [...prev, createMessage("student", assistantReply)]);
      }
      fetchSessions();
    } catch (error) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        createMessage("system", "Connection error. Confirm the FastAPI server is running."),
      ]);
    } finally {
      setIsSending(false);
      if (teachModeDuringSend) {
        if (silentResponse) {
          setTeachStatus("learned");
          teachStatusTimeoutRef.current = window.setTimeout(() => {
            setTeachStatus("idle");
            teachStatusTimeoutRef.current = null;
          }, 2500);
        } else {
          setTeachStatus("idle");
        }
      }
    }
  };

  // Interpret slash commands and call the matching backend route.
  const handleCommand = async (rawCommand: string) => {
    const stripped = rawCommand.slice(1).trim();
    console.log("Command executed:", rawCommand);

    if (!stripped) {
      pushSystemMessage("Type /help to see the available commands.");
      return;
    }

    const [commandToken, ...args] = stripped.split(/\s+/);
    const normalized = commandToken.toLowerCase();

    const appendSystem = (...systemTexts: string[]) => {
      setMessages((prev) => [
        ...prev,
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
        const res = await authedFetch(url.toString(), { method: "POST" });
        if (!res.ok) {
          const text = await res.text();
          appendSystem(`Topic update failed: ${text || res.statusText}`);
          return;
        }
        const data = await res.json();
        appendSystem(data.message ?? `Topic set to '${topic}'.`);
      } catch (error) {
        console.error(error);
        appendSystem("Could not reach the topic endpoint.");
      }
      return;
    }

    if (normalized === "session") {
      const sub = (args[0] || "").toLowerCase();
      if (sub === "new") {
        try {
          const res = await authedFetch(`${API_BASE}/session`, { method: "POST" });
          if (!res.ok) {
            const text = await res.text();
            appendSystem(`Session start failed: ${text || res.statusText}`);
            return;
          }
          const data = await res.json();
          handleNewChat();
          setSessionId(data.session_id ?? null);
          pushSystemMessage(data.message ?? "New session started.");
        } catch (error) {
          console.error(error);
          appendSystem("Could not start a new session.");
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
        const res = await authedFetch(url.toString());
        if (!res.ok) {
          const text = await res.text();
        appendSystem(`Summary failed: ${text || res.statusText}`);
          return;
        }
        const data = await res.json();
        const summary = typeof data.summary === "string" ? data.summary : JSON.stringify(data.summary);
        appendSystem(`Session summary:\n\n${summary}`);
      } catch (error) {
        console.error(error);
        appendSystem("Could not retrieve the summary.");
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
        const res = await authedFetch(url.toString());
        if (!res.ok) {
          const text = await res.text();
          appendSystem(`Topic search failed: ${text || res.statusText}`);
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
        appendSystem(`Memories mentioning “${query}”:\n\n${formatted}`);
      } catch (error) {
        console.error(error);
        appendSystem("Could not reach the search endpoint.");
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
        const res = await authedFetch(url.toString());
        if (!res.ok) {
          const text = await res.text();
          appendSystem(`Search failed: ${text || res.statusText}`);
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
        appendSystem(`Search results for “${query}”:\n\n${formatted}`);
      } catch (error) {
        console.error(error);
        appendSystem("Could not reach the search API.");
      }
      return;
    }

    if (normalized === "vectorsearch") {
      const query = args.join(" ").trim();
      if (!query) {
        appendSystem("Usage: /vectorsearch <query>");
        return;
      }
      try {
        const url = new URL(`${API_BASE}/vectorsearch`);
        url.searchParams.set("query", query);
        const res = await authedFetch(url.toString());
        if (!res.ok) {
          const text = await res.text();
          appendSystem(`Vector search failed: ${text || res.statusText}`);
          return;
        }
        const data = await res.json();
        const results = Array.isArray(data.combined_results) ? data.combined_results : [];
        if (results.length === 0) {
          appendSystem(`No vector hits for “${query}”.`);
          return;
        }
        const formatted = results
          .map(
            (item: any, index: number) =>
              `${index + 1}. [${item?.source ?? "unknown"}] ${item?.memory?.slice?.(0, 200) ?? "—"}... (score: ${
                item?.score?.toFixed?.(3) ?? "?"
              })`
          )
          .join("\n\n");
        appendSystem(`Vector search results for “${query}”:\n\n${formatted}`);
      } catch (error) {
        console.error(error);
        appendSystem("Could not reach the vectorsearch endpoint.");
      }
      return;
    }

    if (normalized === "documentvectorsearch") {
      const query = args.join(" ").trim();
      if (!query) {
        appendSystem("Usage: /documentvectorsearch <query>");
        return;
      }
      try {
        const url = new URL(`${API_BASE}/documentvectorsearch`);
        url.searchParams.set("query", query);
        const res = await authedFetch(url.toString());
        if (!res.ok) {
          const text = await res.text();
          appendSystem(`Document vector search failed: ${text || res.statusText}`);
          return;
        }
        const data = await res.json();
        const results = Array.isArray(data.results) ? data.results : [];
        if (results.length === 0) {
          appendSystem(`No document matches for “${query}”.`);
          return;
        }
        const formatted = results
          .map(
            (item: any, index: number) =>
              `${index + 1}. ${item?.metadata?.title ?? "Untitled"} — ${item?.memory?.slice?.(0, 200) ?? "—"}... (score: ${
                item?.score?.toFixed?.(3) ?? "?"
              })`
          )
          .join("\n\n");
        appendSystem(`Document vector search results for “${query}”:\n\n${formatted}`);
      } catch (error) {
        console.error(error);
        appendSystem("Could not reach the documentvectorsearch endpoint.");
      }
      return;
    }

    if (normalized === "all") {
      try {
        const res = await authedFetch(`${API_BASE}/all`);
        if (!res.ok) {
          const text = await res.text();
        appendSystem(`Fetch failed: ${text || res.statusText}`);
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
        appendSystem(`Complete memory listing:\n\n${formatted}`);
      } catch (error) {
        console.error(error);
        appendSystem("Could not fetch stored memories.");
      }
      return;
    }

    if (normalized === "reset") {
      try {
        const res = await authedFetch(`${API_BASE}/reset`, { method: "POST" });
        if (!res.ok) {
          const text = await res.text();
        appendSystem(`Reset failed: ${text || res.statusText}`);
          return;
        }
        const data = await res.json();
        appendSystem(data?.message ?? "Memory reset complete.");
      } catch (error) {
        console.error(error);
        appendSystem("Could not reach the reset endpoint.");
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

  // When clicking a suggestion, seed the textarea with its syntax.
  const applyCommandTemplate = (command: CommandDefinition) => {
    const template = command.usage.endsWith(" ") ? command.usage : `${command.usage} `;
    setInput(template);
    setCommandQuery("");
    setShowSuggestions(false);
  };

  // Show a simple loader until the auth hook resolves current status.
  if (authChecking) {
    return (
      <div className="app-loading-shell">
        <div className="app-loading-card">
          <p className="app-loading-label">Verifying session…</p>
          <div className="app-loading-dots">
            <span />
            <span />
            <span />
          </div>
        </div>
      </div>
    );
  }

  // Route the standalone terms page outside the chat shell.
  if (pathNormalized === "/terms") {
    return <TermsPage />;
  }

  // Render login or signup shells for unauthenticated visitors.
  if (!isAuthenticated) {
    if (pathNormalized === "/signup") {
      return (
        <AuthShell title="AI Buddy" subtitle="Create your account">
          <SignupForm onSubmit={handleSignup} />
        </AuthShell>
      );
    }
    return (
      <AuthShell subtitle="Sign in to continue learning">
        <LoginForm onSubmit={login} />
      </AuthShell>
    );
  }

  // Default authenticated view: chat shell with sidebar + composer.
  return (
    <div className="chat-app">
      <div className="chat-shell">
        <Sidebar
          sessions={sessions}
          activeSessionId={sessionId}
          refreshing={refreshing}
          teachMode={teachMode}
          isSending={isSending}
          isUploading={isUploading}
          editingSession={editingSession}
          newTitle={newTitle}
          onNewChat={handleNewChat}
          onRefresh={() => {
            fetchSessions();
          }}
          onToggleTeachMode={handleToggleTeachMode}
          onSelectSession={handleSelectSession}
          onStartRename={handleStartRename}
          onRenameSubmit={handleRenameSession}
          onRenameCancel={handleRenameCancel}
          onTitleChange={setNewTitle}
          onDeleteSession={handleDeleteSession}
        />

        <main className="chat-main">
          <header className="chat-header">
          <div>
            <h2 className="chat-header-title">AI Buddy</h2>
            <p className="chat-header-subtitle">
              Hi! I'm your AI study companion in a virtual world.
            </p>
          </div>
          <button
            type="button"
            className="primary-button logout-button"
            onClick={() => {
              logout();
              navigate("/login");
            }}
            title="Log out"
          >
            Logout
          </button>
        </header>

          <section className="message-list">
            {messages.map((message) => (
              <article
                key={message.id}
                className={`message-row ${message.role}`}
                aria-label={`${roleMeta[message.role].label} message`}
              >
                <div className={`message-avatar ${message.role}`}>
                  {roleMeta[message.role].initial}
                </div>
                <div className={`message-bubble ${message.role}`}>
                  <div className="message-meta">
                    <span className="role">{roleMeta[message.role].label}</span>
                    <span className="time">{formatTime(message.createdAt)}</span>
                  </div>
                  <div className="message-text">{message.text}</div>
                </div>
              </article>
            ))}

            {isSending && (
              <article className="message-row student typing" aria-live="polite">
                <div className="message-avatar student">{roleMeta.student.initial}</div>
                <div className="message-bubble student">
                  <div className="message-meta">
                    <span className="role">{roleMeta.student.label}</span>
                    <span className="time">…</span>
                  </div>
                  <div className={`typing-indicator ${teachMode ? "teach-mode" : ""}`}>
                    {teachMode ? (
                      <span className="teach-mode-text">Learning…</span>
                    ) : (
                      <>
                        <span />
                        <span />
                        <span />
                      </>
                    )}
                  </div>
                </div>
              </article>
            )}

            {teachMode && teachStatus === "learned" && !isSending && (
              <div className="teach-mode-status" role="status" aria-live="polite">
                Learned!
              </div>
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

              <button
                type="button"
                className={`secondary-button chat-mic-button${isRecording ? " recording" : ""}`}
                onClick={isRecording ? stopRecording : startRecording}
                disabled={isTranscribing}
                title={isRecording ? "Stop recording" : "Start voice input"}
                aria-label={isRecording ? "Stop recording" : "Start voice input"}
              >
                {isRecording ? "⏹️" : "🎤"}
              </button>

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
                onClick={playLatestReply}
                disabled={isPlaying || isSending || isTranscribing || !hasAssistantReply}
                title="Play latest assistant reply"
                aria-label="Play latest assistant reply"
              >
                🔊
              </button>
              <button
                type="button"
                className="secondary-button chat-upload-button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading || isSending}
                aria-label="Upload supporting documents"
              >
                {isUploading ? "Uploading…" : "Upload Docs"}
              </button>
              <button type="submit" className="primary-button" disabled={isSending}>
                {isSending ? "Sending…" : "Send"}
              </button>
            </div>
            {audioError && (
              <p style={{ color: "#d14343", marginTop: "0.5rem" }}>{audioError}</p>
            )}
          </form>
        </main>
      </div>
    </div>
  );
}
