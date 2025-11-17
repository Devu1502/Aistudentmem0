import React, { FormEvent, useState } from "react";
import "./LoginForm.css";

export type SignupFormValues = {
  name?: string;
  email: string;
  password: string;
  passwordConfirm: string;
  acceptTerms: boolean;
};

type SignupFormProps = {
  onSubmit: (values: SignupFormValues) => Promise<{ success: boolean; message?: string }>;
};

export const SignupForm = ({ onSubmit }: SignupFormProps) => {
  const [form, setForm] = useState<SignupFormValues>({
    name: "",
    email: "",
    password: "",
    passwordConfirm: "",
    acceptTerms: false,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (field: keyof SignupFormValues, value: string | boolean) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.acceptTerms) {
      setError("Please accept the Terms & Conditions.");
      return;
    }
    if (form.password !== form.passwordConfirm) {
      setError("Passwords do not match.");
      return;
    }
    setError(null);
    setLoading(true);
    const result = await onSubmit(form);
    if (!result.success) {
      setError(result.message ?? "Signup failed.");
    }
    setLoading(false);
  };

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <label className="login-field">
        <span>Name (optional)</span>
        <input
          type="text"
          placeholder="Ada Lovelace"
          value={form.name}
          onChange={(event) => handleChange("name", event.target.value)}
        />
      </label>

      <label className="login-field">
        <span>Email</span>
        <input
          type="email"
          placeholder="you@example.com"
          value={form.email}
          onChange={(event) => handleChange("email", event.target.value)}
          required
        />
      </label>

      <label className="login-field">
        <span>Password</span>
        <input
          type="password"
          placeholder="Create a strong password"
          value={form.password}
          onChange={(event) => handleChange("password", event.target.value)}
          minLength={8}
          required
        />
      </label>

      <label className="login-field">
        <span>Confirm password</span>
        <input
          type="password"
          placeholder="Repeat your password"
          value={form.passwordConfirm}
          onChange={(event) => handleChange("passwordConfirm", event.target.value)}
          minLength={8}
          required
        />
      </label>

      <label className="login-field" style={{ flexDirection: "row", alignItems: "center", gap: "10px" }}>
        <input
          type="checkbox"
          checked={form.acceptTerms}
          onChange={(event) => handleChange("acceptTerms", event.target.checked)}
          required
        />
        <span style={{ fontSize: "0.85rem" }}>
          I agree to the{" "}
          <a href="/terms" target="_blank" rel="noreferrer">
            Terms & Conditions
          </a>
          .
        </span>
      </label>

      {error && <p className="login-error">{error}</p>}

      <button type="submit" className="login-submit" disabled={loading}>
        {loading ? "Creating account…" : "Create account"}
      </button>

      <div className="login-helper-row">
        <a href="/login">Already have an account?</a>
      </div>
    </form>
  );
};
