import React, { ReactNode } from "react";
import "../AuthShell.css";

type AuthShellProps = {
  title?: string;
  subtitle?: string;
  children: ReactNode;
};

export const AuthShell = ({ title = "AI Buddy", subtitle = "Sign in to continue", children }: AuthShellProps) => {
  return (
    <div className="auth-shell">
      <div className="auth-shell-card">
        <header className="auth-shell-header">
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </header>
        <div className="auth-shell-body">{children}</div>
      </div>
    </div>
  );
};
