import React, { FormEvent, useState } from "react";
import "./LoginForm.css";

type Props = {
  onSubmit: (email: string) => Promise<{ success: boolean; message?: string }>;
};

export const ForgotPasswordForm = ({ onSubmit }: Props) => {
  const [email, setEmail] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    const result = await onSubmit(email.trim());
    if (result.success) {
      setFeedback("If that email exists, a reset link has been sent.");
    } else {
      setError(result.message ?? "Unable to process request.");
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

      {error && <p className="login-error">{error}</p>}
      {feedback && <p style={{ color: "#c4b5fd", fontSize: "0.85rem", margin: 0 }}>{feedback}</p>}

      <button type="submit" className="login-submit" disabled={loading}>
        {loading ? "Sending reset link…" : "Send reset link"}
      </button>

      <div className="login-helper-row">
        <a href="/login">Return to login</a>
        <a href="/signup">Create account</a>
      </div>
    </form>
  );
};
