"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import DeckStage from "../../../components/share/DeckStage";
import PresentMode from "../../../components/share/PresentMode";
import RecipientShell from "../../../components/share/RecipientShell";
import { resolveShare, type ShareProjection } from "../../../lib/api";

export default function SharePage() {
  const params = useParams();
  const token = params.token as string;
  const [projection, setProjection] = useState<ShareProjection | null>(null);
  const [error, setError] = useState<{ status: number; detail: string } | null>(null);
  const [slideIdx, setSlideIdx] = useState(0);
  const [presenting, setPresenting] = useState(false);

  const load = useCallback(async () => {
    try {
      setProjection(await resolveShare(token));
    } catch (e) {
      const err = e as Error & { status?: number };
      setError({ status: err.status ?? 500, detail: err.message });
    }
  }, [token]);

  useEffect(() => {
    load();
    // Poll every 30s so view_count + content refreshes match real-world activity.
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, [load]);

  if (error) {
    const isExpired = error.status === 410;
    const isMissing = error.status === 404;
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 px-6 text-center">
        <h1 className="font-display text-[28px] font-semibold text-foreground">
          {isExpired ? "This share link has expired" : isMissing ? "Share link not found" : "Couldn't load share"}
        </h1>
        <p className="text-[13px] text-muted">{error.detail}</p>
      </div>
    );
  }

  if (!projection) {
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  }

  const targetType = projection.share.target_type;
  const isDeck = !!projection.deck && projection.deck.length > 0;

  // Workspace target — the legacy "share the whole stash" view.
  if (targetType === "workspace") {
    return (
      <>
        <RecipientShell
          projection={projection}
          token={token}
          onPresent={isDeck ? () => setPresenting(true) : undefined}
        >
          <div className="mx-auto max-w-3xl">
            <div className="mb-4 text-[11px] uppercase tracking-[0.2em] text-brand">
              {isDeck ? "Deck" : "Stash"}
            </div>
            <h1 className="font-display text-[34px] font-bold tracking-tight text-foreground">
              {projection.stash?.name}
            </h1>
            {projection.stash?.summary && (
              <p className="mt-2 text-[14px] text-dim">{projection.stash.summary}</p>
            )}

            {isDeck && projection.deck && (
              <div className="mt-6">
                <DeckStage
                  slides={projection.deck}
                  current={slideIdx}
                  onChange={setSlideIdx}
                />
              </div>
            )}

            {!isDeck && projection.narrative && (
              <article className="markdown-content mt-6 rounded-2xl border border-border bg-surface px-6 py-6">
                <pre className="whitespace-pre-wrap font-sans text-[14px] leading-relaxed text-foreground">
                  {projection.narrative.body}
                </pre>
              </article>
            )}

            {(projection.pages ?? []).length > 0 && (
              <div className="mt-8">
                <h2 className="font-display text-[16px] font-semibold text-foreground">Pages</h2>
                <ul className="mt-3 flex flex-col gap-2">
                  {projection.pages!.map((p) => (
                    <li key={p.id} className="rounded-lg border border-border-subtle bg-surface px-4 py-3 text-[13px]">
                      <div className="font-medium text-foreground">{p.name}</div>
                      <pre className="mt-2 whitespace-pre-wrap font-sans text-[12px] text-dim">
                        {p.body.slice(0, 600)}
                        {p.body.length > 600 ? "…" : ""}
                      </pre>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {(projection.files ?? []).length > 0 && (
              <div className="mt-8">
                <h2 className="font-display text-[16px] font-semibold text-foreground">Files</h2>
                <ul className="mt-3 flex flex-col gap-1.5 text-[13px]">
                  {projection.files!.map((f) => (
                    <li key={f.id} className="text-foreground">
                      📄 {f.name}{" "}
                      <span className="text-muted">({(f.size_bytes / 1024).toFixed(1)} KB)</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </RecipientShell>

        {presenting && projection.deck && (
          <PresentMode slides={projection.deck} onExit={() => setPresenting(false)} />
        )}
      </>
    );
  }

  // Session target — show summary + artifacts + chat thread.
  if (targetType === "session" && projection.session) {
    const s = projection.session;
    return (
      <RecipientShell projection={projection} token={token}>
        <div className="mx-auto max-w-3xl">
          <div className="mb-4 text-[11px] uppercase tracking-[0.2em] text-brand">Session</div>
          <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
            #{s.session_id.replace(/^acme-/, "")}
          </h1>
          <p className="mt-1.5 text-[12px] text-muted">
            {s.agent_name} · {(projection.events ?? []).length} events
            {s.finished_at ? " · finished" : " · in progress"}
          </p>
          {s.summary && (
            <article className="markdown-content mt-6 rounded-2xl border border-border bg-surface px-6 py-6 text-[14px] leading-relaxed text-foreground whitespace-pre-wrap">
              {s.summary}
            </article>
          )}
          {(projection.artifacts ?? []).length > 0 && (
            <div className="mt-8">
              <h2 className="font-display text-[14px] font-semibold text-foreground">Files touched</h2>
              <ul className="mt-2 flex flex-col gap-1 font-mono text-[12px] text-dim">
                {projection.artifacts!.map((a) => (
                  <li key={a.id}>{a.file_path}</li>
                ))}
              </ul>
            </div>
          )}
          {(projection.events ?? []).length > 0 && (
            <div className="mt-8 flex flex-col gap-3">
              {projection.events!.map((e) => (
                <div key={e.id} className="flex gap-3 rounded-md px-2 py-2">
                  <span className="w-16 text-[10px] font-mono uppercase tracking-wide text-muted pt-0.5">
                    {e.role}
                  </span>
                  <div className="min-w-0 flex-1">
                    {e.tool_name && (
                      <span className="mb-1 inline-block rounded bg-indigo-50 px-1 py-0 font-mono text-[10px] text-indigo-700 ring-1 ring-indigo-200">
                        {e.tool_name}
                      </span>
                    )}
                    <div className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-foreground">
                      {e.content}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </RecipientShell>
    );
  }

  // Page target — single page in read-only.
  if (targetType === "page" && projection.page) {
    const p = projection.page;
    return (
      <RecipientShell projection={projection} token={token}>
        <div className="mx-auto max-w-3xl">
          <div className="mb-4 text-[11px] uppercase tracking-[0.2em] text-brand">Page</div>
          <h1 className="font-display text-[34px] font-bold tracking-tight text-foreground">
            {p.name.replace(/\.md$/, "")}
          </h1>
          <article className="markdown-content mt-6 text-[15px] leading-relaxed text-foreground whitespace-pre-wrap">
            {p.body}
          </article>
        </div>
      </RecipientShell>
    );
  }

  // Folder target — folder + immediate children.
  if (targetType === "folder" && projection.folder) {
    return (
      <RecipientShell projection={projection} token={token}>
        <div className="mx-auto max-w-3xl">
          <div className="mb-4 text-[11px] uppercase tracking-[0.2em] text-brand">Folder</div>
          <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
            📁 {projection.folder.name}
          </h1>
          {(projection.subfolders ?? []).length > 0 && (
            <div className="mt-6">
              <h2 className="font-display text-[14px] font-semibold text-foreground">Subfolders</h2>
              <ul className="mt-2 flex flex-col gap-1 text-[13px]">
                {projection.subfolders!.map((sf) => (
                  <li key={sf.id} className="text-foreground">📁 {sf.name}</li>
                ))}
              </ul>
            </div>
          )}
          {(projection.pages ?? []).length > 0 && (
            <div className="mt-6">
              <h2 className="font-display text-[14px] font-semibold text-foreground">Pages</h2>
              <ul className="mt-2 flex flex-col gap-1 text-[13px]">
                {projection.pages!.map((p) => (
                  <li key={p.id} className="text-foreground">📄 {p.name}</li>
                ))}
              </ul>
            </div>
          )}
          {(projection.files ?? []).length > 0 && (
            <div className="mt-6">
              <h2 className="font-display text-[14px] font-semibold text-foreground">Files</h2>
              <ul className="mt-2 flex flex-col gap-1 text-[13px]">
                {projection.files!.map((f) => (
                  <li key={f.id} className="text-foreground">
                    📄 {f.name} <span className="text-muted">({(f.size_bytes / 1024).toFixed(1)} KB)</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </RecipientShell>
    );
  }

  // File target — link to download/preview.
  if (targetType === "file" && projection.file) {
    const f = projection.file;
    return (
      <RecipientShell projection={projection} token={token}>
        <div className="mx-auto max-w-3xl">
          <div className="mb-4 text-[11px] uppercase tracking-[0.2em] text-brand">File</div>
          <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
            📄 {f.name}
          </h1>
          <p className="mt-2 text-[12px] text-muted">
            {f.content_type} · {(f.size_bytes / 1024).toFixed(1)} KB
          </p>
          {f.url && (
            <a
              href={f.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-4 inline-block rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[13px] font-medium text-white hover:bg-[var(--color-brand-700)]"
            >
              Open file
            </a>
          )}
        </div>
      </RecipientShell>
    );
  }

  return (
    <div className="flex h-screen items-center justify-center text-muted">
      Unknown share target.
    </div>
  );
}
