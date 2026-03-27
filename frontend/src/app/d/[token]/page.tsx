"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { getDeckByToken, getDeckContent, verifyDeckAccess } from "../../../lib/api";

const HEARTBEAT_INTERVAL = 30000;

export default function DeckViewerPage() {
  const params = useParams();
  const token = params.token as string;

  const [meta, setMeta] = useState<{ deck_name: string; deck_type: string; require_email: boolean; has_passcode: boolean; allow_download: boolean } | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const heartbeatRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const m = await getDeckByToken(token);
        setMeta(m);
        if (!m.require_email && !m.has_passcode) {
          const content = await getDeckContent(token);
          setHtml(content.html_content);
          setSessionToken(content.session_token);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Deck not found");
      }
      setLoading(false);
    })();
  }, [token]);

  // Heartbeat: send every 30s while viewing
  const sendHeartbeat = useCallback(async () => {
    if (!sessionToken) return;
    try {
      await fetch(`/api/v1/d/${token}/heartbeat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_token: sessionToken }),
      });
    } catch { /* ignore */ }
  }, [token, sessionToken]);

  useEffect(() => {
    if (!sessionToken) return;
    heartbeatRef.current = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL);

    // Pause when tab hidden
    const handleVisibility = () => {
      if (document.hidden) {
        if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      } else {
        heartbeatRef.current = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL);
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    // Final heartbeat on unload
    const handleUnload = () => {
      if (sessionToken) {
        navigator.sendBeacon(
          `/api/v1/d/${token}/heartbeat`,
          JSON.stringify({ session_token: sessionToken }),
        );
      }
    };
    window.addEventListener("beforeunload", handleUnload);

    return () => {
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("beforeunload", handleUnload);
    };
  }, [sessionToken, sendHeartbeat, token]);

  const handleVerify = async () => {
    setError("");
    try {
      const content = await verifyDeckAccess(token, email || undefined, passcode || undefined);
      setHtml(content.html_content);
      setSessionToken(content.session_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    }
  };

  const handleDownload = () => {
    window.open(`/api/v1/d/${token}/download`, "_blank");
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center bg-white text-gray-400">Loading...</div>;
  }

  if (error && !meta) {
    return <div className="min-h-screen flex items-center justify-center bg-white text-gray-500">{error}</div>;
  }

  if (html) {
    return (
      <div className="h-screen flex flex-col">
        {/* Branded header */}
        <div className="h-10 flex-shrink-0 bg-white border-b border-gray-200 flex items-center justify-between px-4">
          <a href="https://getboozle.com" target="_blank" rel="noopener noreferrer" className="text-sm font-bold tracking-tight text-gray-900" style={{ fontFamily: "'Satoshi', sans-serif" }}>
            boozle
          </a>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">{meta?.deck_name}</span>
            {meta?.allow_download && (
              <button onClick={handleDownload} className="text-xs text-gray-500 hover:text-gray-900">
                Download
              </button>
            )}
          </div>
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

  // Gate
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white rounded-lg shadow-lg p-8 w-full max-w-sm">
        <h1 className="text-xl font-semibold text-gray-900 mb-1">{meta?.deck_name}</h1>
        <p className="text-gray-500 text-sm mb-6">
          {meta?.require_email && meta?.has_passcode
            ? "Enter your email and passcode to view."
            : meta?.require_email
              ? "Enter your email to view."
              : "Enter the passcode to view."}
        </p>
        {error && <p className="text-red-500 text-sm mb-3">{error}</p>}
        {meta?.require_email && (
          <input
            type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="Your email"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:border-orange-500"
          />
        )}
        {meta?.has_passcode && (
          <input
            type="password" value={passcode} onChange={(e) => setPasscode(e.target.value)}
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
