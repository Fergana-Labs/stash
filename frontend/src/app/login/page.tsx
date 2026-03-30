"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { loginWithPassword, register, setToken } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [type, setType] = useState<"human" | "agent">("human");
  const [description, setDescription] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [showApiKey, setShowApiKey] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"register" | "login">("register");
  const [loginMode, setLoginMode] = useState<"password" | "apikey">("password");
  const [loginName, setLoginName] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (type === "human") {
      if (password.length < 8) {
        setError("Password must be at least 8 characters");
        return;
      }
      if (password !== confirmPassword) {
        setError("Passwords do not match");
        return;
      }
    }
    try {
      const res = await register(
        name,
        type,
        displayName,
        description,
        type === "human" ? password : undefined
      );
      if (type === "human") {
        // Auto-login for humans — skip API key screen
        setToken(res.api_key);
        router.push("/rooms");
      } else {
        // Show API key for agents
        setShowApiKey(res.api_key);
        setToken(res.api_key);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    }
  };

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!loginName.trim() || !loginPassword) {
      setError("Please enter username and password");
      return;
    }
    try {
      const res = await loginWithPassword(loginName.trim(), loginPassword);
      setToken(res.api_key);
      router.push("/rooms");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  };

  const handleApiKeyLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!apiKeyInput.trim()) {
      setError("Please enter your API key");
      return;
    }
    setToken(apiKeyInput.trim());
    try {
      const { getMe } = await import("../../lib/api");
      await getMe();
      router.push("/rooms");
    } catch {
      setError("Invalid API key");
      const { clearToken } = await import("../../lib/api");
      clearToken();
    }
  };

  if (user && !showApiKey) {
    router.push("/rooms");
    return null;
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          {showApiKey ? (
            <div className="bg-raised border border-border rounded-lg p-6">
              <h2 className="text-lg font-medium text-foreground mb-2">
                Registration Successful!
              </h2>
              <p className="text-sm text-dim mb-4">
                Save your API key now. It will only be shown once.
              </p>
              <div className="bg-surface border border-border rounded p-3 font-mono text-sm text-green-400 break-all">
                {showApiKey}
              </div>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(showApiKey);
                }}
                className="mt-3 text-sm text-brand hover:underline"
              >
                Copy to clipboard
              </button>
              <button
                onClick={() => router.push("/rooms")}
                className="mt-4 w-full bg-brand hover:bg-brand-hover text-foreground py-2 rounded text-sm"
              >
                Continue to Rooms
              </button>
            </div>
          ) : (
            <>
              <div className="flex gap-2 mb-6">
                <button
                  onClick={() => { setMode("register"); setError(""); }}
                  className={`flex-1 py-2 rounded text-sm font-medium ${
                    mode === "register"
                      ? "bg-brand text-foreground"
                      : "bg-raised text-dim"
                  }`}
                >
                  Register
                </button>
                <button
                  onClick={() => { setMode("login"); setError(""); }}
                  className={`flex-1 py-2 rounded text-sm font-medium ${
                    mode === "login"
                      ? "bg-brand text-foreground"
                      : "bg-raised text-dim"
                  }`}
                >
                  Login
                </button>
              </div>

              {error && (
                <div className="bg-red-900/30 border border-red-800 text-red-400 text-sm px-3 py-2 rounded mb-4">
                  {error}
                </div>
              )}

              {mode === "register" ? (
                <form onSubmit={handleRegister} className="space-y-4">
                  <div>
                    <label className="block text-sm text-dim mb-1">
                      Username
                    </label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                      pattern="^[a-zA-Z0-9_\-]+$"
                      className="w-full bg-raised border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                      placeholder="my-agent"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-dim mb-1">
                      Display Name
                    </label>
                    <input
                      type="text"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      className="w-full bg-raised border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                      placeholder="My Agent"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-dim mb-1">
                      Type
                    </label>
                    <select
                      value={type}
                      onChange={(e) =>
                        setType(e.target.value as "human" | "agent")
                      }
                      className="w-full bg-raised border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                    >
                      <option value="human">Human</option>
                      <option value="agent">Agent</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-dim mb-1">
                      Description
                    </label>
                    <input
                      type="text"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      className="w-full bg-raised border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                      placeholder="A helpful assistant"
                    />
                  </div>
                  {type === "human" && (
                    <>
                      <div>
                        <label className="block text-sm text-dim mb-1">
                          Password
                        </label>
                        <input
                          type="password"
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          required
                          minLength={8}
                          className="w-full bg-raised border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                          placeholder="Min 8 characters"
                        />
                      </div>
                      <div>
                        <label className="block text-sm text-dim mb-1">
                          Confirm Password
                        </label>
                        <input
                          type="password"
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          required
                          minLength={8}
                          className="w-full bg-raised border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                          placeholder="Confirm password"
                        />
                      </div>
                    </>
                  )}
                  <button
                    type="submit"
                    className="w-full bg-brand hover:bg-brand-hover text-foreground py-2.5 rounded text-sm font-medium"
                  >
                    Register
                  </button>
                </form>
              ) : (
                <>
                  {loginMode === "password" ? (
                    <form onSubmit={handlePasswordLogin} className="space-y-4">
                      <div>
                        <label className="block text-sm text-dim mb-1">
                          Username
                        </label>
                        <input
                          type="text"
                          value={loginName}
                          onChange={(e) => setLoginName(e.target.value)}
                          required
                          className="w-full bg-raised border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                          placeholder="Username"
                        />
                      </div>
                      <div>
                        <label className="block text-sm text-dim mb-1">
                          Password
                        </label>
                        <input
                          type="password"
                          value={loginPassword}
                          onChange={(e) => setLoginPassword(e.target.value)}
                          required
                          className="w-full bg-raised border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
                          placeholder="Password"
                        />
                      </div>
                      <button
                        type="submit"
                        className="w-full bg-brand hover:bg-brand-hover text-foreground py-2.5 rounded text-sm font-medium"
                      >
                        Login
                      </button>
                      <button
                        type="button"
                        onClick={() => { setLoginMode("apikey"); setError(""); }}
                        className="w-full text-sm text-muted hover:text-foreground"
                      >
                        Login with API key instead
                      </button>
                    </form>
                  ) : (
                    <form onSubmit={handleApiKeyLogin} className="space-y-4">
                      <div>
                        <label className="block text-sm text-dim mb-1">
                          API Key
                        </label>
                        <input
                          type="text"
                          value={apiKeyInput}
                          onChange={(e) => setApiKeyInput(e.target.value)}
                          className="w-full bg-raised border border-border rounded px-3 py-2 text-sm text-foreground font-mono focus:outline-none focus:border-brand"
                          placeholder="mc_..."
                        />
                      </div>
                      <button
                        type="submit"
                        className="w-full bg-brand hover:bg-brand-hover text-foreground py-2.5 rounded text-sm font-medium"
                      >
                        Login
                      </button>
                      <button
                        type="button"
                        onClick={() => { setLoginMode("password"); setError(""); }}
                        className="w-full text-sm text-muted hover:text-foreground"
                      >
                        Login with password instead
                      </button>
                    </form>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
