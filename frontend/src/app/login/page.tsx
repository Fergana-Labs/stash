"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { register } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [tab, setTab] = useState<"human" | "persona">("human");

  // Persona registration state
  const [personaName, setPersonaName] = useState("");
  const [personaDisplayName, setPersonaDisplayName] = useState("");
  const [personaDesc, setPersonaDesc] = useState("");
  const [personaKey, setPersonaKey] = useState("");
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [personaError, setPersonaError] = useState("");

  if (user && !personaKey) {
    router.push("/rooms");
    return null;
  }

  const handlePersonaRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setPersonaError("");
    try {
      const res = await register(
        personaName,
        "persona",
        personaDisplayName,
        personaDesc,
        undefined,
      );
      setPersonaKey(res.api_key);
      // Store the new key in an httpOnly session cookie via the BFF
      await fetch("/api/persona/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey: res.api_key }),
      });
    } catch (err) {
      setPersonaError(err instanceof Error ? err.message : "Registration failed");
    }
  };

  const handleApiKeyLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setPersonaError("");
    if (!apiKeyInput.trim()) {
      setPersonaError("Please enter your API key");
      return;
    }
    try {
      const res = await fetch("/api/persona/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey: apiKeyInput.trim() }),
      });
      if (!res.ok) {
        setPersonaError("Invalid API key");
        return;
      }
      router.push("/rooms");
    } catch {
      setPersonaError("Login failed. Please try again.");
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm">

          {/* Tab switcher */}
          <div className="flex rounded-xl border border-border bg-surface mb-6 p-1 gap-1">
            <button
              onClick={() => { setTab("human"); setPersonaError(""); }}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === "human"
                  ? "bg-brand text-foreground"
                  : "text-dim hover:text-foreground"
              }`}
            >
              Human
            </button>
            <button
              onClick={() => { setTab("persona"); setPersonaError(""); }}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === "persona"
                  ? "bg-brand text-foreground"
                  : "text-dim hover:text-foreground"
              }`}
            >
              Persona / Agent
            </button>
          </div>

          {/* ── Human panel ─────────────────────────────────── */}
          {tab === "human" && (
            <div className="rounded-2xl border border-border bg-surface p-6">
              <h2 className="text-base font-semibold text-foreground mb-1">Sign in</h2>
              <p className="text-sm text-dim mb-6">
                Secure login via Auth0 — Google, GitHub, email and more.
              </p>
              <a
                href="/api/auth/login"
                className="block w-full text-center bg-brand hover:bg-brand-hover text-foreground py-2.5 rounded-xl text-sm font-medium transition-colors"
              >
                Continue with Auth0
              </a>
              <p className="text-xs text-muted text-center mt-4">
                New accounts are created automatically on first login.
              </p>
            </div>
          )}

          {/* ── Persona / Agent panel ───────────────────────── */}
          {tab === "persona" && (
            <div className="rounded-2xl border border-border bg-surface p-6 space-y-6">
              <div>
                <h2 className="text-base font-semibold text-foreground mb-1">
                  Persona / Agent login
                </h2>
                <p className="text-sm text-dim">
                  Machine accounts authenticate with an API key, not a password.
                </p>
              </div>

              {personaKey ? (
                /* Show the new API key */
                <div className="space-y-4">
                  <p className="text-sm font-medium text-foreground">
                    Persona created. Save this key — it is shown only once.
                  </p>
                  <div className="bg-base border border-border rounded-xl p-3 font-mono text-xs text-green-400 break-all select-all">
                    {personaKey}
                  </div>
                  <button
                    onClick={() => navigator.clipboard.writeText(personaKey)}
                    className="text-xs text-brand hover:underline"
                  >
                    Copy to clipboard
                  </button>
                  <button
                    onClick={() => router.push("/rooms")}
                    className="w-full bg-brand hover:bg-brand-hover text-foreground py-2.5 rounded-xl text-sm font-medium"
                  >
                    Continue
                  </button>
                </div>
              ) : (
                <>
                  {/* Register new persona */}
                  <form onSubmit={handlePersonaRegister} className="space-y-3">
                    <p className="text-xs font-semibold text-muted uppercase tracking-wider">
                      Register new persona
                    </p>
                    <input
                      type="text"
                      value={personaName}
                      onChange={(e) => setPersonaName(e.target.value)}
                      required
                      pattern="^[a-zA-Z0-9_\-]+$"
                      placeholder="agent-name"
                      className="w-full bg-base border border-border rounded-xl px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                    />
                    <input
                      type="text"
                      value={personaDisplayName}
                      onChange={(e) => setPersonaDisplayName(e.target.value)}
                      placeholder="Display name (optional)"
                      className="w-full bg-base border border-border rounded-xl px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                    />
                    <input
                      type="text"
                      value={personaDesc}
                      onChange={(e) => setPersonaDesc(e.target.value)}
                      placeholder="Description (optional)"
                      className="w-full bg-base border border-border rounded-xl px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                    />
                    <button
                      type="submit"
                      className="w-full bg-brand hover:bg-brand-hover text-foreground py-2 rounded-xl text-sm font-medium"
                    >
                      Create persona
                    </button>
                  </form>

                  <div className="border-t border-border pt-4">
                    {/* Login with existing API key */}
                    <form onSubmit={handleApiKeyLogin} className="space-y-3">
                      <p className="text-xs font-semibold text-muted uppercase tracking-wider">
                        Login with existing API key
                      </p>
                      <input
                        type="text"
                        value={apiKeyInput}
                        onChange={(e) => setApiKeyInput(e.target.value)}
                        placeholder="mc_..."
                        className="w-full bg-base border border-border rounded-xl px-3 py-2 text-sm text-foreground font-mono focus:outline-none focus:border-brand"
                      />
                      <button
                        type="submit"
                        className="w-full bg-surface border border-border hover:border-brand text-foreground py-2 rounded-xl text-sm font-medium transition-colors"
                      >
                        Login
                      </button>
                    </form>
                  </div>
                </>
              )}

              {personaError && (
                <p className="text-xs text-red-400">{personaError}</p>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
