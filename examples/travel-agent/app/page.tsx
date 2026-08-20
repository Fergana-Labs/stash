"use client";

import { useCallback, useEffect, useState } from "react";

type Org = {
  id: string;
  external_id: string;
  name: string;
  session_count: number;
};
type Turn = { role: "you" | "planner"; text: string };
type Session = { name: string; transcript: string };

// A failed route answers with JSON too, but a crash upstream may not — read
// the body as text first so the page shows what happened instead of a parse
// error about the error.
async function load<T>(url: string, init?: RequestInit): Promise<T & { error?: string }> {
  const res = await fetch(url, init);
  const body = await res.text();
  let data = {} as T & { error?: string };
  try {
    data = body ? JSON.parse(body) : {};
  } catch {
    throw new Error(
      `${url} → ${res.status}: ${body.slice(0, 300) || "(empty response)"}`,
    );
  }
  if (!res.ok) throw new Error(data.error ?? `${url} → ${res.status}`);
  return data;
}

export default function Home() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [org, setOrg] = useState<Org | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session] = useState(
    () => `web-${Math.random().toString(36).slice(2, 10)}`,
  );

  useEffect(() => {
    load<{ orgs: Org[] }>("/api/orgs")
      .then((d) => {
        setOrgs(d.orgs ?? []);
        setOrg((current) => current ?? d.orgs?.[0] ?? null);
      })
      .catch((e) => setError(e.message));
  }, []);

  const loadTranscripts = useCallback((external: string) => {
    load<{ sessions: Session[] }>(`/api/transcript?org=${encodeURIComponent(external)}`)
      .then((d) => setSessions(d.sessions ?? []))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (org) loadTranscripts(org.external_id);
  }, [org, loadTranscripts]);

  // Replaces the old python demo.py: the same scripted scenario, run by the
  // app so there is one implementation of the integration, not two.
  async function seed() {
    setSeeding(true);
    setError(null);
    try {
      await load("/api/seed", { method: "POST" });
      const d = await load<{ orgs: Org[] }>("/api/orgs");
      setOrgs(d.orgs ?? []);
      setOrg(d.orgs?.find((o) => o.external_id === "globetrek") ?? d.orgs?.[0] ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSeeding(false);
    }
  }

  async function ask() {
    if (!org || !question.trim()) return;
    const asked = question;
    setQuestion("");
    setTurns((t) => [...t, { role: "you", text: asked }]);
    setBusy(true);
    setError(null);
    try {
      // Two independent calls, as a real integration has them: the agent
      // reads and answers with only an org id, then the transcript is uploaded
      // separately — which is why the session id appears in the second call
      // and nowhere in the first.
      const data = await load<{ reply: string }>("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ org: org.external_id, question: asked }),
      });
      await load("/api/record", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          org: org.external_id,
          orgName: org.name,
          session: `${org.external_id}:${session}`,
          question: asked,
          reply: data.reply,
        }),
      });
      setTurns((t) => [...t, { role: "planner", text: data.reply }]);
      loadTranscripts(org.external_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 24px" }}>
      <h1
        style={{
          font: "600 26px/1.2 ui-sans-serif, system-ui",
          color: "#16130F",
          margin: 0,
        }}
      >
        Travel planner
      </h1>
      <p style={{ marginTop: 8, color: "#7C7469" }}>
        One planner, many agencies. Each agency is an org: its travellers are
        private, what the planner learns about the world is shared.
      </p>

      <div
        style={{ display: "flex", gap: 8, margin: "24px 0", flexWrap: "wrap" }}
      >
        {orgs.map((o) => (
          <button
            key={o.id}
            onClick={() => {
              setOrg(o);
              setTurns([]);
            }}
            style={{
              padding: "8px 14px",
              borderRadius: 4,
              cursor: "pointer",
              border: `1px solid ${o.id === org?.id ? "#FF5A36" : "#E9E5DC"}`,
              background: o.id === org?.id ? "rgba(255,90,54,0.10)" : "#F4F2EC",
              color: o.id === org?.id ? "#FF5A36" : "#453F37",
              font: "500 14px ui-sans-serif, system-ui",
            }}
          >
            {o.name}
            <span
              style={{
                marginLeft: 8,
                opacity: 0.7,
                fontFamily: "ui-monospace, monospace",
                fontSize: 12,
              }}
            >
              {o.external_id}
            </span>
          </button>
        ))}
      </div>

      <div style={{ marginBottom: 20 }}>
        <button
          onClick={() => void seed()}
          disabled={seeding}
          style={{
            padding: "8px 14px",
            borderRadius: 4,
            border: "1px solid #E9E5DC",
            background: "#F4F2EC",
            font: "500 14px ui-sans-serif, system-ui",
            cursor: "pointer",
          }}
        >
          {seeding ? "Seeding — this makes four real calls…" : "Seed the demo scenario"}
        </button>
        <span style={{ marginLeft: 12, color: "#A79E92", fontSize: 13 }}>
          Wanderly learns a visa lesson the hard way; Globetrek asks about its own trip.
        </span>
      </div>

      {error && (
        <p
          style={{
            color: "#C4421F",
            background: "rgba(255,90,54,0.07)",
            padding: "10px 14px",
            borderRadius: 4,
          }}
        >
          {error}
        </p>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 24,
          alignItems: "start",
        }}
      >
        <section>
          <h2 style={sectionStyle}>Chat as {org?.name ?? "…"}</h2>
          <div style={panelStyle}>
            {turns.length === 0 && (
              <p style={{ color: "#A79E92", margin: 0 }}>
                Ask the planner something.
              </p>
            )}
            {turns.map((t, i) => (
              <p key={i} style={{ margin: "0 0 12px" }}>
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: 12,
                    color: t.role === "you" ? "#7C7469" : "#FF5A36",
                  }}
                >
                  {t.role}
                </span>
                <br />
                {t.text}
              </p>
            ))}
            {busy && <p style={{ color: "#A79E92", margin: 0 }}>thinking…</p>}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !busy && ask()}
              placeholder="Client wants Vietnam in 3 weeks. Is the e-visa going to make it?"
              style={{
                flex: 1,
                padding: "10px 12px",
                borderRadius: 4,
                border: "1px solid #E9E5DC",
                background: "#fff",
                font: "14px ui-sans-serif, system-ui",
              }}
            />
            <button
              onClick={ask}
              disabled={busy}
              style={{
                padding: "10px 18px",
                borderRadius: 4,
                border: "none",
                background: "#FF5A36",
                color: "#fff",
                font: "500 14px ui-sans-serif, system-ui",
                cursor: "pointer",
              }}
            >
              Ask
            </button>
          </div>
        </section>

        <section>
          <h2 style={sectionStyle}>
            What {org?.name ?? "this agency"} can see
          </h2>
          <div style={panelStyle}>
            {sessions.length === 0 && (
              <p style={{ color: "#A79E92", margin: 0 }}>No transcripts yet.</p>
            )}
            {sessions.map((s) => (
              <details key={s.name} style={{ marginBottom: 10 }}>
                <summary style={{ cursor: "pointer", color: "#16130F" }}>
                  {s.name}
                </summary>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    font: "12px/1.5 ui-monospace, monospace",
                    color: "#7C7469",
                    marginTop: 8,
                  }}
                >
                  {s.transcript}
                </pre>
              </details>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

const sectionStyle = {
  font: "600 15px ui-sans-serif, system-ui",
  color: "#16130F",
  margin: "0 0 10px",
} as const;
const panelStyle = {
  border: "1px solid #E9E5DC",
  background: "#fff",
  borderRadius: 4,
  padding: 16,
  minHeight: 220,
  maxHeight: 460,
  overflowY: "auto",
} as const;
