"use client";
import { useState } from "react";
import { supabase } from "../../lib/supabaseClient";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        data: { business_name: businessName || undefined },
        emailRedirectTo: typeof window !== "undefined" ? `${window.location.origin}/upload` : undefined,
      },
    });
    if (error) setError(error.message);
    else setSent(true);
  };

  return (
    <div style={{ maxWidth: 380, margin: "80px auto", padding: 24 }}>
<h1 style={{ fontSize: 22, marginBottom: 4 }}>Vantage</h1>
      <p style={{ color: "#7C8797", marginBottom: 24, fontSize: 14 }}>
        Your solution for business growth — sign in with your email, no password needed.
      </p>

      {sent ? (
        <div style={{ background: "#151B24", border: "1px solid #262F3C", borderRadius: 10, padding: 16, fontSize: 14 }}>
          Check <strong>{email}</strong> for a magic sign-in link.
        </div>
      ) : (
        <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <input
            type="text"
            placeholder="Business name (e.g. Imrahs)"
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            style={inputStyle}
          />
          <input
            type="email"
            required
            placeholder="you@business.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={inputStyle}
          />
          <button type="submit" style={buttonStyle}>Send magic link</button>
          {error && <div style={{ color: "#F0576B", fontSize: 13 }}>{error}</div>}
        </form>
      )}
    </div>
  );
}

const inputStyle = {
  background: "#151B24", border: "1px solid #262F3C", borderRadius: 8,
  padding: "10px 12px", color: "#EAEDF2", fontSize: 14, outline: "none",
};
const buttonStyle = {
  background: "#2DD4BF", border: "none", borderRadius: 8, padding: "10px 12px",
  color: "#0D1117", fontWeight: 600, cursor: "pointer", fontSize: 14,
};
