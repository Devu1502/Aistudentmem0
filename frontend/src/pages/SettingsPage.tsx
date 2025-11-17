import { AuthShell } from "../components/AuthShell";
import type { AuthUser } from "../hooks/useAuth";
import { API_BASE } from "../apiConfig";

type SettingsPageProps = {
  user: AuthUser | null;
  token: string | null;
  onNavigate: (path: string) => void;
  onLogout: () => void;
};

export default function SettingsPage({ user, token, onNavigate, onLogout }: SettingsPageProps) {
  if (!user) {
    return (
      <AuthShell title="Not signed in" subtitle="Please log in to view your settings.">
        <button type="button" className="primary-button" onClick={() => onNavigate("/login")}>
          Go to Login
        </button>
      </AuthShell>
    );
  }

  const handleAvatarUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !token) {
      return;
    }
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/auth/avatar`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) {
        const text = await res.text();
        alert(text || "Failed to upload avatar");
        return;
      }
      alert("Avatar updated");
    } catch (error) {
      console.error("Avatar upload failed", error);
      alert("Unable to upload avatar right now");
    }
  };

  return (
    <AuthShell title="Account Settings" subtitle={user.email}>
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: "6px", color: "#e2e8f0" }}>
          Profile Picture
          <input type="file" accept="image/*" onChange={handleAvatarUpload} />
        </label>
        <button type="button" className="secondary-button" onClick={() => onNavigate("/terms")}>
          View Terms & Conditions
        </button>
        <button type="button" className="secondary-button" onClick={onLogout}>
          Log out
        </button>
        <button type="button" className="primary-button" onClick={() => onNavigate("/")}>
          Back to Chat
        </button>
      </div>
    </AuthShell>
  );
}
