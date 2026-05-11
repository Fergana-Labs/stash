"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  getStashSpine,
  listMyWorkspaces,
  listPublicWorkspaces,
  type StashSpine,
} from "../lib/api";
import type { User, Workspace } from "../lib/types";

interface AppSidebarProps {
  user?: User;
  onLogout?: () => void;
  collapsed?: boolean;
  cmdkOpen?: boolean;
  onCmdkOpen?: () => void;
}

interface StashNode extends Workspace {
  shared?: boolean;
}

function Chevron() {
  return (
    <svg
      className="chev h-3 w-3 text-muted"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function NavRow({
  href,
  icon,
  label,
  active,
  trailing,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  trailing?: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={
        "page-row flex items-center gap-2 rounded-md px-2 py-1 text-[13px] transition-colors " +
        (active
          ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)]"
          : "text-dim hover:bg-raised hover:text-foreground")
      }
    >
      <span className="flex h-4 w-4 items-center justify-center text-[14px]">{icon}</span>
      <span className="flex-1 truncate">{label}</span>
      {trailing}
    </Link>
  );
}

function StashTree({
  stash,
  spine,
  defaultOpen,
  onOpen,
  pathname,
}: {
  stash: StashNode;
  spine: StashSpine | null;
  defaultOpen: boolean;
  onOpen: () => void;
  pathname: string;
}) {
  const isActive = pathname === `/stashes/${stash.id}`;

  return (
    <details
      open={defaultOpen}
      onToggle={(e) => {
        if ((e.target as HTMLDetailsElement).open) onOpen();
      }}
      className="group/stash"
    >
      <summary className="page-row flex items-center gap-1 rounded-md px-2 py-1 text-[13px] hover:bg-raised">
        <Chevron />
        <span className="text-[14px]">📊</span>
        <Link
          href={`/stashes/${stash.id}`}
          className={
            "flex-1 truncate font-medium " +
            (isActive ? "text-[var(--color-brand-800)]" : "text-foreground")
          }
        >
          {stash.name}
        </Link>
      </summary>
      <div className="ml-3 space-y-0.5 border-l border-border pl-2">
        <NavRow
          href={
            spine?.narrative
              ? `/stashes/${stash.id}/p/${spine.narrative.id}`
              : `/stashes/${stash.id}`
          }
          icon="📌"
          label="Narrative"
          active={isActive}
          trailing={
            <span className="rounded bg-surface px-1 py-0 text-[9px] font-medium uppercase tracking-wide text-muted ring-1 ring-border">
              readme
            </span>
          }
        />
        <div className="my-1 ml-3.5 h-px bg-border" />

        <details open className="text-[13px]">
          <summary className="page-row flex items-center gap-1 rounded-md px-2 py-1 hover:bg-raised">
            <Chevron />
            <span className="text-[14px]">💬</span>
            <span className="flex-1 truncate font-medium text-foreground">Sessions</span>
            <span className="text-[10.5px] text-muted">{spine?.sessions.length ?? 0}</span>
          </summary>
          <div className="ml-3 space-y-0.5 border-l border-border pl-2">
            {spine?.sessions.slice(0, 8).map((s) => (
              <NavRow
                key={s.session_id}
                href={`/stashes/${stash.id}/sessions/${encodeURIComponent(s.session_id)}`}
                icon={<span className="text-muted">#</span>}
                label={s.session_id.length > 22 ? s.session_id.slice(0, 22) + "…" : s.session_id}
              />
            ))}
            {(!spine || spine.sessions.length === 0) && (
              <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
            )}
          </div>
        </details>

        <details open className="text-[13px]">
          <summary className="page-row flex items-center gap-1 rounded-md px-2 py-1 hover:bg-raised">
            <Chevron />
            <span className="text-[14px]">📖</span>
            <span className="flex-1 truncate font-medium text-foreground">Wiki</span>
            <span className="text-[10.5px] text-muted">
              {(spine?.root_pages?.length ?? 0) +
                (spine?.skills.length ?? 0) +
                (spine?.drive.folders.length ?? 0) +
                (spine?.drive.files.length ?? 0)}
            </span>
          </summary>
          <div className="ml-3 space-y-0.5 border-l border-border pl-2">
            {spine?.skills.map((s) => (
              <details key={s.folder_id} className="text-[12.5px]">
                <summary className="page-row flex items-center gap-1 rounded-md px-2 py-0.5 hover:bg-raised">
                  <Chevron />
                  <span className="text-muted">📁</span>
                  <Link
                    href={`/stashes/${stash.id}/skills/${encodeURIComponent(s.name)}`}
                    className="flex-1 truncate text-left text-foreground hover:text-[var(--color-brand-700)]"
                  >
                    {s.name}
                  </Link>
                </summary>
                <div className="ml-2.5 space-y-0.5 border-l border-border pl-2">
                  {s.files.map((f) => (
                    <NavRow
                      key={f}
                      href={`/stashes/${stash.id}/skills/${encodeURIComponent(s.name)}?file=${encodeURIComponent(f)}`}
                      icon={<span className="text-muted">📄</span>}
                      label={f}
                    />
                  ))}
                </div>
              </details>
            ))}
            {spine?.drive.folders.slice(0, 4).map((f) => (
              <NavRow
                key={f.id}
                href={`/files?ws=${stash.id}`}
                icon={<span className="text-muted">📁</span>}
                label={f.name}
              />
            ))}
            {spine?.root_pages?.slice(0, 10).map((p) => (
              <NavRow
                key={p.id}
                href={`/stashes/${stash.id}/p/${p.id}`}
                icon={<span className="text-muted">📄</span>}
                label={p.name}
              />
            ))}
            {spine?.drive.files.slice(0, 12).map((f) => {
              const isCsvLinked =
                f.content_type?.includes("csv") && f.linked_table_id;
              const href = isCsvLinked
                ? `/tables/${f.linked_table_id}?workspaceId=${stash.id}`
                : `/stashes/${stash.id}/f/${f.id}`;
              return (
                <NavRow
                  key={f.id}
                  href={href}
                  icon={
                    <span
                      className={
                        f.content_type?.includes("pdf")
                          ? "text-rose-500"
                          : f.content_type?.includes("csv")
                          ? "text-emerald-600"
                          : f.content_type?.includes("html")
                          ? "text-amber-600"
                          : "text-muted"
                      }
                    >
                      {f.content_type?.includes("csv") ? "▦" : "📄"}
                    </span>
                  }
                  label={f.name}
                />
              );
            })}
            {(!spine ||
              ((spine.root_pages?.length ?? 0) === 0 &&
                spine.skills.length === 0 &&
                spine.drive.files.length === 0 &&
                spine.drive.folders.length === 0)) && (
              <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
            )}
          </div>
        </details>
      </div>
    </details>
  );
}

export default function AppSidebar({ user, collapsed, onCmdkOpen }: AppSidebarProps) {
  const pathname = usePathname();
  const activeStashId = pathname.match(/^\/stashes\/([^/]+)/)?.[1] ?? null;
  const [mine, setMine] = useState<Workspace[]>([]);
  const [shared, setShared] = useState<Workspace[]>([]);
  const [openStashes, setOpenStashes] = useState<Record<string, boolean>>({});
  const [spines, setSpines] = useState<Record<string, StashSpine>>({});

  useEffect(() => {
    listMyWorkspaces()
      .then((r) => setMine(r.workspaces ?? []))
      .catch(() => {});
    listPublicWorkspaces()
      .then((r) => {
        if (!user) return;
        setShared((r.workspaces ?? []).filter((w) => w.creator_id !== user.id).slice(0, 6));
      })
      .catch(() => {});
  }, [user?.id]);

  useEffect(() => {
    const m = pathname.match(/^\/stashes\/([^/]+)/);
    if (m?.[1]) {
      setOpenStashes((s) => ({ ...s, [m[1]]: true }));
      if (!spines[m[1]]) {
        getStashSpine(m[1])
          .then((sp) => setSpines((all) => ({ ...all, [m[1]]: sp })))
          .catch(() => {});
      }
    }
  }, [pathname, spines]);

  function handleOpen(stashId: string) {
    setOpenStashes((s) => ({ ...s, [stashId]: true }));
    if (!spines[stashId]) {
      getStashSpine(stashId)
        .then((sp) => setSpines((all) => ({ ...all, [stashId]: sp })))
        .catch(() => {});
    }
  }

  if (collapsed) return null;

  return (
    <aside className="scroll-thin overflow-y-auto border-r border-border bg-surface">
      <div className="px-3 pb-1 pt-3">
        <Link href="/" className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/octopus.svg" alt="Stash" className="h-7 w-7" />
          <span className="font-display text-[14px] font-semibold tracking-tight text-foreground">
            stash
          </span>
        </Link>
      </div>

      <nav className="px-2 pt-2 text-[13px]">
        <button
          onClick={onCmdkOpen}
          className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-muted hover:bg-raised"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          Search
          <span className="ml-auto rounded bg-base px-1 py-0 font-mono text-[10px] text-muted ring-1 ring-border">
            ⌘K
          </span>
        </button>
        <NavRow
          href="/discover"
          icon={<span>◐</span>}
          label="Discover"
          active={pathname.startsWith("/discover")}
        />
        <NavRow
          href={activeStashId ? `/stashes/${activeStashId}/activity` : "/memory"}
          icon={<span>⏱</span>}
          label="Activity"
          active={pathname.startsWith("/memory") || pathname.includes("/activity")}
        />
      </nav>

      {shared.length > 0 && (
        <>
          <div className="mt-4 flex items-center justify-between px-3 pb-1">
            <span className="text-[11px] font-semibold tracking-wide text-muted">
              SHARED WITH ME
            </span>
          </div>
          <nav className="px-1 text-[13.5px]">
            {shared.map((s) => (
              <StashTree
                key={s.id}
                stash={{ ...s, shared: true }}
                spine={spines[s.id] ?? null}
                defaultOpen={!!openStashes[s.id]}
                onOpen={() => handleOpen(s.id)}
                pathname={pathname}
              />
            ))}
          </nav>
        </>
      )}

      <div className="mt-4 flex items-center justify-between px-3 pb-1">
        <span className="text-[11px] font-semibold tracking-wide text-muted">MY STASHES</span>
        <Link
          href="/stashes/new"
          className="rounded p-0.5 text-muted hover:bg-base hover:text-foreground"
          title="New stash"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </Link>
      </div>
      <nav className="px-1 text-[13.5px]">
        {mine.map((s) => (
          <StashTree
            key={s.id}
            stash={s}
            spine={spines[s.id] ?? null}
            defaultOpen={!!openStashes[s.id]}
            onOpen={() => handleOpen(s.id)}
            pathname={pathname}
          />
        ))}
        {mine.length === 0 && (
          <div className="px-3 py-1.5 text-[12px] italic text-muted">
            No stashes yet —{" "}
            <Link href="/stashes/new" className="text-[var(--color-brand-700)] underline">
              create one
            </Link>
          </div>
        )}
      </nav>

      <div className="mt-6 border-t border-border px-2 py-2">
        <NavRow href="/docs" icon={<span>?</span>} label="Docs" active={pathname.startsWith("/docs")} />
        <NavRow href="/settings" icon={<span>⚙</span>} label="Settings" active={pathname.startsWith("/settings")} />
      </div>
    </aside>
  );
}
