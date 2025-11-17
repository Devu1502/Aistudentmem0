import React, { FormEvent, useState } from "react";
import "./LoginForm.css";

type Props = {
  onSubmit: (email: string, password: string) => Promise<{ success: boolean; message?: string }>;
};

export const LoginForm = ({ onSubmit }: Props) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setLoading(true);
    const result = await onSubmit(email.trim(), password);
    if (!result.success) {
      setError(result.message ?? "Login failed.");
    }
    setLoading(false);
  };

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <label className="login-field">
        <span>Email</span>
        <input
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
      </label>

      <label className="login-field">
        <span>Password</span>
        <input
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          minLength={8}
          required
        />
      </label>

      {error && <p className="login-error">{error}</p>}

      <button type="submit" className="login-submit" disabled={loading}>
        {loading ? "Signing in…" : "Sign in"}
      </button>

      <div className="login-helper-row">
        <a href="/signup">Create account</a>
      </div>
    </form>
  );
};
