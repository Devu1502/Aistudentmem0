import { AuthShell } from "../components/AuthShell";

export default function TermsPage() {
  return (
    <AuthShell title="Terms & Conditions" subtitle="">
      <div
        style={{
          color: "#e2e8f0",
          lineHeight: "1.6",
          fontSize: "0.9rem",
          maxHeight: "60vh",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
        }}
      >
        <p>• Users must follow responsible AI use guidelines.</p>
        <p>• No harmful or illegal usage of AI Buddy.</p>
        <p>• Data stored under each account remains private to the user.</p>
        <p>• Chat history is isolated per account and never shared.</p>
        <p>• Uploaded documents and avatars belong solely to the user.</p>
      </div>
    </AuthShell>
  );
}
