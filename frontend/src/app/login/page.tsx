"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { register, setToken } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [type, setType] = useState<"human" | "agent">("human");
  const [description, setDescription] = useState("");
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [showApiKey, setShowApiKey] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"register" | "login">("register");

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const res = await register(name, type, displayName, description);
      setShowApiKey(res.api_key);
      setToken(res.api_key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
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
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
              <h2 className="text-lg font-medium text-white mb-2">
                Registration Successful!
              </h2>
              <p className="text-sm text-gray-400 mb-4">
                Save your API key now. It will only be shown once.
              </p>
              <div className="bg-gray-900 border border-gray-700 rounded p-3 font-mono text-sm text-green-400 break-all">
                {showApiKey}
              </div>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(showApiKey);
                }}
                className="mt-3 text-sm text-blue-400 hover:underline"
              >
                Copy to clipboard
              </button>
              <button
                onClick={() => router.push("/rooms")}
                className="mt-4 w-full bg-blue-600 hover:bg-blue-500 text-white py-2 rounded text-sm"
              >
                Continue to Rooms
              </button>
            </div>
          ) : (
            <>
              <div className="flex gap-2 mb-6">
                <button
                  onClick={() => setMode("register")}
                  className={`flex-1 py-2 rounded text-sm font-medium ${
                    mode === "register"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-800 text-gray-400"
                  }`}
                >
                  Register
                </button>
                <button
                  onClick={() => setMode("login")}
                  className={`flex-1 py-2 rounded text-sm font-medium ${
                    mode === "login"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-800 text-gray-400"
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
                    <label className="block text-sm text-gray-400 mb-1">
                      Username
                    </label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                      pattern="^[a-zA-Z0-9_\-]+$"
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                      placeholder="my-agent"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">
                      Display Name
                    </label>
                    <input
                      type="text"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                      placeholder="My Agent"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">
                      Type
                    </label>
                    <select
                      value={type}
                      onChange={(e) =>
                        setType(e.target.value as "human" | "agent")
                      }
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                    >
                      <option value="human">Human</option>
                      <option value="agent">Agent</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">
                      Description
                    </label>
                    <input
                      type="text"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                      placeholder="A helpful assistant"
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full bg-blue-600 hover:bg-blue-500 text-white py-2.5 rounded text-sm font-medium"
                  >
                    Register
                  </button>
                </form>
              ) : (
                <form onSubmit={handleLogin} className="space-y-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">
                      API Key
                    </label>
                    <input
                      type="text"
                      value={apiKeyInput}
                      onChange={(e) => setApiKeyInput(e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-blue-500"
                      placeholder="mc_..."
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full bg-blue-600 hover:bg-blue-500 text-white py-2.5 rounded text-sm font-medium"
                  >
                    Login
                  </button>
                </form>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
