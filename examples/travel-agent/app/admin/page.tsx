"use client";

import { useCallback, useEffect, useState } from "react";
import { Compass } from "../icons";

type Traveller = { id: string; name: string; email: string; chats: string[] };
type State = { travellers: Traveller[]; wiki: string[] };

export default function Admin() {
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch("/api/admin/state");
    const body = await res.json();
    if (!res.ok) return setNotice(body.error);
    setState(body);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function reset() {
    setBusy(true);
    setNotice(null);
    const res = await fetch("/api/admin/reset", { method: "POST" });
    const body = await res.json();
    setBusy(false);
    if (!res.ok) return setNotice(body.error);
    setNotice(`Deleted ${body.purged} conversation${body.purged === 1 ? "" : "s"} and put Sam's back.`);
    await load();
  }

  return (
    <main className="admin">
      <header className="admin-head">
        <Compass />
        <span className="brand-name">Atlas</span>
        <span className="admin-tag">demo control</span>
      </header>

      <section className="panel">
        <h1 className="panel-title">Reset to the opening position</h1>
        <p className="panel-note">
          Deletes every conversation both travellers have, then writes Sam&apos;s Vietnam thread
          back: he asks whether three weeks is enough, comes back to say the e-visa actually took
          19 working days, and mentions he will not fly overnight. Priya is left with nothing, so
          her first question about Vietnam is genuinely her first.
        </p>
        <p className="panel-note">
          The shared wiki is left alone — it is what the curator already built out of Sam&apos;s
          lesson, and it is what makes Priya&apos;s answer land. Rebuilding it means another
          curator run from the Stash console.
        </p>
        <button className="danger" onClick={() => void reset()} disabled={busy}>
          {busy ? "Resetting…" : "Reset demo"}
        </button>
        {notice && <p className="panel-notice">{notice}</p>}
      </section>

      <section className="panel">
        <h2 className="panel-title">Right now</h2>
        {!state && <p className="panel-note">Reading…</p>}
        {state?.travellers.map((traveller) => (
          <div key={traveller.id} className="admin-row">
            <div className="admin-who">
              <div className="workspace-name">{traveller.name}</div>
              <div className="workspace-plan">{traveller.email}</div>
            </div>
            <ul className="admin-chats">
              {traveller.chats.length === 0 && <li className="admin-empty">no conversations</li>}
              {traveller.chats.map((chat) => (
                <li key={chat}>{chat}</li>
              ))}
            </ul>
          </div>
        ))}
        {state && (
          <div className="admin-row">
            <div className="admin-who">
              <div className="workspace-name">Shared wiki</div>
              <div className="workspace-plan">/memory — every traveller sees this</div>
            </div>
            <ul className="admin-chats">
              {state.wiki.length === 0 && <li className="admin-empty">empty</li>}
              {state.wiki.map((page) => (
                <li key={page}>{page}</li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </main>
  );
}
