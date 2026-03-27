"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getDeckByToken, getDeckContent, verifyDeckAccess } from "../../../lib/api";

export default function DeckViewerPage() {
  const params = useParams();
  const token = params.token as string;

  const [meta, setMeta] = useState<{ deck_name: string; require_email: boolean; has_passcode: boolean } | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const m = await getDeckByToken(token);
        setMeta(m);
        // Try to get content directly (no gates)
        if (!m.require_email && !m.has_passcode) {
          const content = await getDeckContent(token);
          setHtml(content.html_content);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Deck not found");
      }
      setLoading(false);
    })();
  }, [token]);

  const handleVerify = async () => {
    setError("");
    try {
      const content = await verifyDeckAccess(token, email || undefined, passcode || undefined);
      setHtml(content.html_content);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center bg-white text-gray-400">Loading...</div>;
  }

  if (error && !meta) {
    return <div className="min-h-screen flex items-center justify-center bg-white text-gray-500">{error}</div>;
  }

  // If HTML loaded, render with branded header + iframe
  if (html) {
    return (
      <div className="h-screen flex flex-col">
        <div className="h-10 flex-shrink-0 bg-white border-b border-gray-200 flex items-center px-4">
          <a href="https://getboozle.com" target="_blank" rel="noopener noreferrer" className="text-sm font-bold tracking-tight text-gray-900" style={{ fontFamily: "'Satoshi', sans-serif" }}>
            boozle
          </a>
        </div>
        <iframe
          srcDoc={html}
          className="flex-1 w-full border-0"
          sandbox="allow-scripts allow-same-origin"
          title={meta?.deck_name || "Deck"}
        />
      </div>
    );
  }

  // Gate: ask for email/passcode
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white rounded-lg shadow-lg p-8 w-full max-w-sm">
        <h1 className="text-xl font-semibold text-gray-900 mb-1">{meta?.deck_name}</h1>
        <p className="text-gray-500 text-sm mb-6">This deck requires verification to view.</p>
        {error && <p className="text-red-500 text-sm mb-3">{error}</p>}
        {meta?.require_email && (
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Your email"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:border-orange-500"
          />
        )}
        {meta?.has_passcode && (
          <input
            type="password"
            value={passcode}
            onChange={(e) => setPasscode(e.target.value)}
            placeholder="Passcode"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:border-orange-500"
          />
        )}
        <button
          onClick={handleVerify}
          className="w-full bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          View Deck
        </button>
      </div>
    </div>
  );
}
