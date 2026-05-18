"use client";

import { useParams } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import StashCard from "../../../../components/stash/StashCard";
import { useShareModal } from "../../../../lib/shareModalContext";
import { addExternalStash, ApiError, listStashes, type WorkspaceStash } from "../../../../lib/api";
import { stashSlugFromInput } from "../../../../lib/stashLinks";

type Filter = "all" | "workspace" | "private" | "public" | "external";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "workspace", label: "Workspace" },
  { key: "private", label: "Private" },
  { key: "public", label: "Public" },
  { key: "external", label: "External" },
];

const COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"];

export default function WorkspaceStashesPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const shareModal = useShareModal();
  const shareVersion = shareModal.version;

  const [stashes, setStashes] = useState<WorkspaceStash[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const list = await listStashes(workspaceId);
      setStashes(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load Stashes");
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load, shareVersion]);

  const counts = useMemo(() => {
    const list = stashes ?? [];
    return {
      all: list.length,
      workspace: list.filter((s) => s.access === "workspace" && !s.is_external).length,
      private: list.filter((s) => s.access === "private").length,
      public: list.filter((s) => s.access === "public").length,
      external: list.filter((s) => s.is_external).length,
    };
  }, [stashes]);

  const filtered = useMemo(() => {
    if (!stashes) return [];
    const ordered = [...stashes].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );
    if (filter === "all") return ordered;
    if (filter === "external") return ordered.filter((s) => s.is_external);
    return ordered.filter((s) => s.access === filter && !s.is_external);
  }, [stashes, filter]);

  const native = useMemo(
    () => filtered.filter((s) => !s.forked_from_stash_id),
    [filtered]
  );
  const forked = useMemo(
    () => filtered.filter((s) => !!s.forked_from_stash_id),
    [filtered]
  );

  if (stashes === null) {
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  }

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1120px] px-12 pb-20 pt-8">
        <div className="flex items-center justify-between gap-4">
          <h1 className="m-0 font-display text-[34px] font-bold tracking-[-0.02em]">
            Stashes
          </h1>
          <button
            type="button"
            onClick={() => shareModal.open({ workspaceId, tab: "new" })}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-brand-600)] px-2.5 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
          >
            <PlusGlyph /> New Stash
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        {/* Toolbar */}
        <div className="mt-5 flex flex-wrap items-center gap-2 border-b border-border pb-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            {FILTERS.map((f) => {
              const active = filter === f.key;
              const count = counts[f.key];
              return (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setFilter(f.key)}
                  className={
                    "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12.5px] " +
                    (active
                      ? "bg-raised font-semibold text-foreground"
                      : "text-muted hover:text-foreground")
                  }
                >
                  {f.key !== "all" && <VisDot vis={f.key} />}
                  {f.label}
                  <span className="sys-label" style={{ fontSize: 10 }}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <ExternalStashLinkForm
          workspaceId={workspaceId}
          onAdded={() => {
            setFilter("external");
            void load();
          }}
        />

        {/* Grid */}
        {filtered.length === 0 ? (
          <div className="mt-12 rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[12.5px] text-muted">
            {stashes.length === 0
              ? "No Stashes yet."
              : "No Stashes match this filter."}
          </div>
        ) : filter === "all" && forked.length > 0 && native.length > 0 ? (
          <>
            <StashGroup title="Workspace Stashes" stashes={native} startIndex={0} />
            <StashGroup
              title="Forked Stashes"
              stashes={forked}
              startIndex={native.length}
            />
          </>
        ) : (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((stash, i) => (
              <StashCard
                key={stash.id}
                stash={stash}
                cover={COVERS[i % COVERS.length]}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ExternalStashLinkForm({
  workspaceId,
  onAdded,
}: {
  workspaceId: string;
  onAdded: () => void;
}) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const slug = stashSlugFromInput(input);
    if (!slug) {
      setError("Paste a Stash URL like /stashes/product-plan or a Stash slug.");
      setMessage("");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    try {
      const stash = await addExternalStash(slug, workspaceId);
      setInput("");
      setMessage(
        stash.is_external
          ? `Added ${stash.title} to this workspace.`
          : `${stash.title} is already in this workspace.`
      );
      onAdded();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add Stash");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mt-4 rounded-lg border border-border-subtle bg-surface px-3 py-3"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <label className="text-[12px] font-medium text-foreground" htmlFor="external-stash-link">
            Add external Stash by link
          </label>
          <input
            id="external-stash-link"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="https://.../stashes/product-plan"
            className="mt-1 w-full rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-md bg-[var(--color-brand-600)] px-3 py-2 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-45 sm:mt-6"
        >
          {busy ? "Adding…" : "Add Stash"}
        </button>
      </div>
      {error ? <p className="mt-2 text-[12px] text-red-500">{error}</p> : null}
      {message ? <p className="mt-2 text-[12px] text-muted">{message}</p> : null}
    </form>
  );
}

function VisDot({ vis }: { vis: string }) {
  const color =
    vis === "public" ? "#22C55E" : vis === "private" ? "#9CA3AF" : "var(--color-brand-500)";
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: 999,
        background: color,
        display: "inline-block",
      }}
    />
  );
}

function PlusGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}


function StashGroup({
  title,
  stashes,
  startIndex,
}: {
  title: string;
  stashes: WorkspaceStash[];
  startIndex: number;
}) {
  return (
    <section className="mt-5">
      <div className="mb-2 flex items-baseline gap-2">
        <h2 className="m-0 font-display text-[14px] font-semibold">{title}</h2>
        <span className="sys-label" style={{ fontSize: 10.5 }}>
          {stashes.length}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {stashes.map((stash, i) => (
          <StashCard
            key={stash.id}
            stash={stash}
            cover={COVERS[(startIndex + i) % COVERS.length]}
          />
        ))}
      </div>
    </section>
  );
}
