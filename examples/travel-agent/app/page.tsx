"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Tenant = { id: string; external_id: string; name: string };
type Turn = { role: "you" | "planner"; text: string };
type Session = { name: string; transcript: string };

// A failed route answers with JSON too, but a crash upstream may not — read the
// body as text first so the page shows what happened rather than a parse error
// about the error.
async function load<T>(url: string, init?: RequestInit): Promise<T & { error?: string }> {
  const res = await fetch(url, init);
  const body = await res.text();
  let data = {} as T & { error?: string };
  try {
    data = body ? JSON.parse(body) : {};
  } catch {
    throw new Error(`${url} → ${res.status}: ${body.slice(0, 300) || "(empty response)"}`);
  }
  if (!res.ok) throw new Error(data.error ?? `${url} → ${res.status}`);
  return data;
}

export default function Home() {
  const [tenants, setOrgs] = useState<Tenant[]>([]);
  const [tenant, setOrg] = useState<Tenant | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [session] = useState(() => `chat-${Math.random().toString(36).slice(2, 10)}`);
  const endRef = useRef<HTMLDivElement>(null);

  const loadOrgs = useCallback(
    (prefer?: string) =>
      load<{ tenants: Tenant[] }>("/api/tenants")
        .then((d) => {
          setOrgs(d.tenants ?? []);
          setOrg(
            (current) =>
              d.tenants?.find((o) => o.external_id === prefer) ?? current ?? d.tenants?.[0] ?? null,
          );
        })
        .catch((e) => setError(e.message)),
    [],
  );

  useEffect(() => {
    void loadOrgs();
  }, [loadOrgs]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  // The chat window keeps no memory of its own. Switching agency clears it, and
  // the planner still knows what that agency knows — because the memory is in
  // Stash, not in this page.
  function pick(external: string) {
    setOrg(tenants.find((o) => o.external_id === external) ?? null);
    setTurns([]);
    setSessions(null);
  }

  async function ask() {
    if (!tenant || !question.trim() || busy) return;
    const asked = question;
    setQuestion("");
    setTurns((t) => [...t, { role: "you", text: asked }]);
    setBusy(true);
    setError(null);
    try {
      // The agent reads and answers with a tenant id and nothing else…
      const { reply } = await load<{ reply: string }>("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant: tenant.external_id, question: asked }),
      });
      setTurns((t) => [...t, { role: "planner", text: reply }]);
      // …and the transcript upload is its own call, as it is in a real backend.
      await load("/api/record", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant: tenant.external_id,
          tenantName: tenant.name,
          session: `${tenant.external_id}:${session}`,
          question: asked,
          reply,
        }),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function seed() {
    setSeeding(true);
    setError(null);
    try {
      await load("/api/seed", { method: "POST" });
      await loadOrgs("globetrek");
      setTurns([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSeeding(false);
    }
  }

  async function toggleTranscripts() {
    if (sessions) return setSessions(null);
    if (!tenant) return;
    try {
      const d = await load<{ sessions: Session[] }>(
        `/api/transcript?tenant=${encodeURIComponent(tenant.external_id)}`,
      );
      setSessions(d.sessions ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "28px 20px 40px" }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          paddingBottom: 16,
          borderBottom: "1px solid #E9E5DC",
        }}
      >
        <strong style={{ font: "600 16px ui-sans-serif, system-ui", color: "#16130F" }}>
          Travel planner
        </strong>
        <select
          value={tenant?.external_id ?? ""}
          onChange={(e) => pick(e.target.value)}
          style={{
            padding: "5px 8px",
            borderRadius: 4,
            border: "1px solid #E9E5DC",
            background: "#fff",
            font: "13px ui-sans-serif, system-ui",
            color: "#453F37",
          }}
        >
          {tenants.map((o) => (
            <option key={o.id} value={o.external_id}>
              {o.name}
            </option>
          ))}
        </select>
        <div style={{ marginLeft: "auto", display: "flex", gap: 14 }}>
          <button onClick={() => void toggleTranscripts()} style={linkStyle}>
            {sessions ? "Hide transcripts" : "Transcripts"}
          </button>
          <button onClick={() => void seed()} disabled={seeding} style={linkStyle}>
            {seeding ? "Seeding…" : "Seed demo"}
          </button>
        </div>
      </header>

      {error && (
        <p
          style={{
            color: "#C4421F",
            background: "rgba(255,90,54,0.07)",
            padding: "10px 14px",
            borderRadius: 4,
            fontSize: 14,
          }}
        >
          {error}
        </p>
      )}

      {sessions && (
        <section
          style={{
            border: "1px solid #E9E5DC",
            background: "#fff",
            borderRadius: 4,
            padding: 14,
            margin: "16px 0",
          }}
        >
          <div style={{ fontSize: 13, color: "#7C7469", marginBottom: 8 }}>
            Everything {tenant?.name} can see. Switch agency and look again.
          </div>
          {sessions.length === 0 && <div style={{ color: "#A79E92", fontSize: 14 }}>Nothing yet.</div>}
          {sessions.map((s) => (
            <details key={s.name} style={{ marginBottom: 6 }}>
              <summary style={{ cursor: "pointer", fontSize: 14 }}>{s.name}</summary>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  font: "12px/1.5 ui-monospace, monospace",
                  color: "#7C7469",
                  marginTop: 6,
                }}
              >
                {s.transcript || "(this transcript is unreadable — its id contains a slash)"}
              </pre>
            </details>
          ))}
        </section>
      )}

      <div style={{ minHeight: 320, padding: "20px 0" }}>
        {turns.length === 0 && !busy && (
          <p style={{ color: "#A79E92", fontSize: 15 }}>
            Ask {tenant?.name ?? "the planner"} something. It knows what this agency knows.
          </p>
        )}
        {turns.map((t, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: t.role === "you" ? "flex-end" : "flex-start",
              marginBottom: 12,
            }}
          >
            <div
              style={{
                maxWidth: "78%",
                padding: "10px 14px",
                borderRadius: 4,
                background: t.role === "you" ? "#FF5A36" : "#fff",
                color: t.role === "you" ? "#fff" : "#453F37",
                border: t.role === "you" ? "none" : "1px solid #E9E5DC",
                fontSize: 15,
                lineHeight: 1.6,
              }}
            >
              {t.text}
            </div>
          </div>
        ))}
        {busy && <div style={{ color: "#A79E92", fontSize: 14 }}>thinking…</div>}
        <div ref={endRef} />
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void ask()}
          placeholder="Client wants Vietnam in 3 weeks. Is the e-visa going to make it?"
          style={{
            flex: 1,
            padding: "12px 14px",
            borderRadius: 4,
            border: "1px solid #E9E5DC",
            background: "#fff",
            font: "15px ui-sans-serif, system-ui",
          }}
        />
        <button
          onClick={() => void ask()}
          disabled={busy}
          style={{
            padding: "12px 20px",
            borderRadius: 4,
            border: "none",
            background: "#FF5A36",
            color: "#fff",
            font: "500 15px ui-sans-serif, system-ui",
            cursor: "pointer",
          }}
        >
          Send
        </button>
      </div>
    </main>
  );
}

const linkStyle = {
  border: "none",
  background: "none",
  padding: 0,
  color: "#7C7469",
  font: "13px ui-sans-serif, system-ui",
  cursor: "pointer",
} as const;
