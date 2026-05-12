"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createSharedView,
  deleteView,
  getStashSpine,
  listViews,
  materializeSession,
  type StashSpine,
  type StashView,
  type ViewItemSpec,
} from "../../lib/api";
import { useShareModal } from "../../lib/shareModalContext";

type Tab = "new" | "manage";
type Visibility = "link" | "public";

type RowGroup = "Folders" | "Pages" | "Files" | "Tables";
type GroupKey = "Sessions" | RowGroup;

const ROW_GROUP_ORDER: RowGroup[] = ["Folders", "Pages", "Files", "Tables"];

interface SelectableRow {
  key: string;
  object_type: "folder" | "page" | "file" | "table";
  object_id: string;
  label: string;
  sub: string;
  group: RowGroup;
}

interface SessionRow {
  key: string;
  session_id: string;
  label: string;
  sub: string;
}

interface SelectedState {
  rows: Map<string, SelectableRow>;
  sessions: Map<string, SessionRow>;
}

const EMPTY_SELECTED: SelectedState = { rows: new Map(), sessions: new Map() };

function selectedCount(s: SelectedState): number {
  return s.rows.size + s.sessions.size;
}

export default function StashShareModal() {
  const { state, close, bumpVersion } = useShareModal();
  const { open, stashId, stashName, initial, tab: initialTab } = state;

  const [tab, setTab] = useState<Tab>(initialTab ?? "new");
  const [spine, setSpine] = useState<StashSpine | null>(null);
  const [views, setViews] = useState<StashView[]>([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<SelectedState>(EMPTY_SELECTED);
  const [title, setTitle] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("link");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [copiedSlug, setCopiedSlug] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!stashId) return;
    const [spineResult, viewsResult] = await Promise.allSettled([
      getStashSpine(stashId),
      listViews(stashId),
    ]);
    if (spineResult.status === "fulfilled") setSpine(spineResult.value);
    if (viewsResult.status === "fulfilled") setViews(viewsResult.value);
  }, [stashId]);

  useEffect(() => {
    if (!open) return;
    setTab(initialTab ?? "new");
    setSearch("");
    setError("");
    setTitle("");
    setVisibility("link");
    setCopiedSlug(null);
    setSelected(buildInitialSelection(initial));
    refresh();
  }, [open, initialTab, initial, refresh]);

  const rows: SelectableRow[] = useMemo(() => buildRows(spine), [spine]);
  const sessions: SessionRow[] = useMemo(() => buildSessions(spine), [spine]);

  const filteredRows = useMemo(() => filterByLabel(rows, search), [rows, search]);
  const filteredSessions = useMemo(
    () => filterByLabel(sessions, search),
    [sessions, search]
  );

  const onToggleRow = (row: SelectableRow) => {
    setSelected((s) => {
      const rows = new Map(s.rows);
      if (rows.has(row.key)) rows.delete(row.key);
      else rows.set(row.key, row);
      return { ...s, rows };
    });
  };

  const onToggleSession = (row: SessionRow) => {
    setSelected((s) => {
      const sessions = new Map(s.sessions);
      if (sessions.has(row.key)) sessions.delete(row.key);
      else sessions.set(row.key, row);
      return { ...s, sessions };
    });
  };

  const onToggleAllVisible = (
    visibleRows: SelectableRow[],
    visibleSessions: SessionRow[]
  ) => {
    setSelected((s) => {
      const allSelected =
        visibleRows.every((r) => s.rows.has(r.key)) &&
        visibleSessions.every((r) => s.sessions.has(r.key));
      const rows = new Map(s.rows);
      const sessions = new Map(s.sessions);
      if (allSelected) {
        for (const r of visibleRows) rows.delete(r.key);
        for (const r of visibleSessions) sessions.delete(r.key);
      } else {
        for (const r of visibleRows) rows.set(r.key, r);
        for (const r of visibleSessions) sessions.set(r.key, r);
      }
      return { rows, sessions };
    });
  };

  const onClearAll = () => setSelected(EMPTY_SELECTED);

  const onToggleGroupRows = (groupRows: SelectableRow[]) => {
    setSelected((s) => {
      const rows = new Map(s.rows);
      const allSelected = groupRows.every((r) => rows.has(r.key));
      if (allSelected) {
        for (const r of groupRows) rows.delete(r.key);
      } else {
        for (const r of groupRows) rows.set(r.key, r);
      }
      return { ...s, rows };
    });
  };

  const onToggleGroupSessions = (groupSessions: SessionRow[]) => {
    setSelected((s) => {
      const sessions = new Map(s.sessions);
      const allSelected = groupSessions.every((r) => sessions.has(r.key));
      if (allSelected) {
        for (const r of groupSessions) sessions.delete(r.key);
      } else {
        for (const r of groupSessions) sessions.set(r.key, r);
      }
      return { ...s, sessions };
    });
  };

  const total = selectedCount(selected);
  const defaultTitle = useMemo(() => {
    if (total === 0) return "";
    if (total === 1) {
      const only = selected.rows.values().next().value ?? selected.sessions.values().next().value;
      return only?.label ?? "";
    }
    return `Bundle of ${total} items`;
  }, [total, selected]);

  const onSubmit = async () => {
    if (!stashId || total === 0) return;
    setSubmitting(true);
    setError("");
    try {
      const items: ViewItemSpec[] = [];
      let pos = 0;
      for (const row of selected.rows.values()) {
        items.push({
          object_type: row.object_type,
          object_id: row.object_id,
          position: pos++,
        });
      }
      // Sessions become pages via the same materialize flow the history page uses.
      // Idempotent: re-materializing maps to the same wiki page.
      for (const sess of selected.sessions.values()) {
        const m = await materializeSession(stashId, sess.session_id);
        items.push({
          object_type: "page",
          object_id: m.page.id,
          position: pos++,
          label_override: sess.label,
        });
      }
      const finalTitle = title.trim() || defaultTitle;
      const result = await createSharedView(stashId, finalTitle, items, {
        ensure: visibility,
      });
      await navigator.clipboard.writeText(result.url).catch(() => {});
      setCopiedSlug(result.view.slug);
      setSelected(EMPTY_SELECTED);
      setTitle("");
      await refresh();
      bumpVersion();
      setTab("manage");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create share");
    } finally {
      setSubmitting(false);
    }
  };

  const onDelete = async (viewId: string) => {
    if (!confirm("Revoke this share link? Anyone with the URL will get a 404.")) return;
    try {
      await deleteView(viewId);
      setViews((v) => v.filter((x) => x.id !== viewId));
      bumpVersion();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to revoke");
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={close}>
      <div
        className="flex w-full max-w-2xl flex-col rounded-2xl border border-border bg-base shadow-xl"
        style={{ maxHeight: "min(80vh, 720px)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3">
          <div className="flex items-center gap-3">
            <h2 className="font-display text-[15px] font-semibold text-foreground">
              Share {stashName || "stash"}
            </h2>
            <div className="flex rounded-md border border-border bg-surface text-[12px]">
              <TabButton active={tab === "new"} onClick={() => setTab("new")}>
                New share
              </TabButton>
              <TabButton
                active={tab === "manage"}
                onClick={() => setTab("manage")}
                badge={views.length}
              >
                Manage
              </TabButton>
            </div>
          </div>
          <button onClick={close} className="text-muted hover:text-foreground" aria-label="Close">
            ✕
          </button>
        </div>

        {tab === "new" ? (
          <NewShareTab
            search={search}
            setSearch={setSearch}
            filteredRows={filteredRows}
            filteredSessions={filteredSessions}
            selected={selected}
            onToggleRow={onToggleRow}
            onToggleSession={onToggleSession}
            onToggleAllVisible={onToggleAllVisible}
            onClearAll={onClearAll}
            onToggleGroupRows={onToggleGroupRows}
            onToggleGroupSessions={onToggleGroupSessions}
            title={title}
            setTitle={setTitle}
            placeholderTitle={defaultTitle}
            visibility={visibility}
            setVisibility={setVisibility}
            submitting={submitting}
            onSubmit={onSubmit}
            total={total}
            error={error}
          />
        ) : (
          <ManageTab
            views={views}
            onDelete={onDelete}
            copiedSlug={copiedSlug}
            setCopiedSlug={setCopiedSlug}
            error={error}
          />
        )}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  badge,
  children,
}: {
  active: boolean;
  onClick: () => void;
  badge?: number;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={
        "flex items-center gap-1.5 px-3 py-1 transition-colors " +
        (active
          ? "bg-[var(--color-brand-600)] text-white"
          : "text-foreground hover:bg-raised")
      }
    >
      {children}
      {typeof badge === "number" && badge > 0 && (
        <span
          className={
            "rounded-full px-1.5 text-[10px] font-mono " +
            (active ? "bg-white/25 text-white" : "bg-base text-muted ring-1 ring-border")
          }
        >
          {badge}
        </span>
      )}
    </button>
  );
}

function NewShareTab(props: {
  search: string;
  setSearch: (v: string) => void;
  filteredRows: SelectableRow[];
  filteredSessions: SessionRow[];
  selected: SelectedState;
  onToggleRow: (r: SelectableRow) => void;
  onToggleSession: (r: SessionRow) => void;
  onToggleAllVisible: (rows: SelectableRow[], sessions: SessionRow[]) => void;
  onClearAll: () => void;
  onToggleGroupRows: (rows: SelectableRow[]) => void;
  onToggleGroupSessions: (sessions: SessionRow[]) => void;
  title: string;
  setTitle: (v: string) => void;
  placeholderTitle: string;
  visibility: Visibility;
  setVisibility: (v: Visibility) => void;
  submitting: boolean;
  onSubmit: () => void;
  total: number;
  error: string;
}) {
  const {
    search,
    setSearch,
    filteredRows,
    filteredSessions,
    selected,
    onToggleRow,
    onToggleSession,
    onToggleAllVisible,
    onClearAll,
    onToggleGroupRows,
    onToggleGroupSessions,
    title,
    setTitle,
    placeholderTitle,
    visibility,
    setVisibility,
    submitting,
    onSubmit,
    total,
    error,
  } = props;

  const [collapsed, setCollapsed] = useState<Set<GroupKey>>(new Set());
  const toggleCollapse = (g: GroupKey) =>
    setCollapsed((c) => {
      const next = new Set(c);
      if (next.has(g)) next.delete(g);
      else next.add(g);
      return next;
    });

  const grouped = useMemo(() => {
    const out: Record<RowGroup, SelectableRow[]> = {
      Folders: [],
      Pages: [],
      Files: [],
      Tables: [],
    };
    for (const r of filteredRows) out[r.group].push(r);
    return out;
  }, [filteredRows]);

  const visibleTotal = filteredRows.length + filteredSessions.length;
  const visibleSelected =
    filteredRows.reduce((n, r) => n + (selected.rows.has(r.key) ? 1 : 0), 0) +
    filteredSessions.reduce((n, r) => n + (selected.sessions.has(r.key) ? 1 : 0), 0);

  const allLabel = search.trim()
    ? `Select all matching (${visibleTotal})`
    : `Select all (${visibleTotal})`;

  return (
    <>
      <div className="border-b border-border-subtle px-5 py-3">
        <input
          autoFocus
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search pages, files, folders, sessions…"
          className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-[13px] text-foreground placeholder:text-muted focus:border-[var(--color-brand-400)] focus:outline-none"
        />
      </div>

      {visibleTotal > 0 && (
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-2">
          <TriCheckbox
            checked={visibleSelected > 0 && visibleSelected === visibleTotal}
            indeterminate={visibleSelected > 0 && visibleSelected < visibleTotal}
            onChange={() => onToggleAllVisible(filteredRows, filteredSessions)}
            label={allLabel}
          />
          {total > 0 && (
            <button
              onClick={onClearAll}
              className="text-[11.5px] text-muted hover:text-foreground"
            >
              Clear ({total})
            </button>
          )}
        </div>
      )}

      <div className="scroll-thin flex-1 overflow-y-auto px-5 py-3">
        {filteredSessions.length > 0 && (
          <GroupBlock
            title="Sessions"
            count={filteredSessions.length}
            collapsed={collapsed.has("Sessions")}
            onToggleCollapse={() => toggleCollapse("Sessions")}
            allSelected={filteredSessions.every((s) => selected.sessions.has(s.key))}
            onToggleSelectAll={() => onToggleGroupSessions(filteredSessions)}
          >
            {filteredSessions.map((s) => (
              <Row
                key={s.key}
                checked={selected.sessions.has(s.key)}
                onToggle={() => onToggleSession(s)}
                label={s.label}
                sub={s.sub}
                tag="session"
              />
            ))}
          </GroupBlock>
        )}
        {ROW_GROUP_ORDER.map((g) =>
          grouped[g].length === 0 ? null : (
            <GroupBlock
              key={g}
              title={g}
              count={grouped[g].length}
              collapsed={collapsed.has(g)}
              onToggleCollapse={() => toggleCollapse(g)}
              allSelected={grouped[g].every((r) => selected.rows.has(r.key))}
              onToggleSelectAll={() => onToggleGroupRows(grouped[g])}
            >
              {grouped[g].map((r) => (
                <Row
                  key={r.key}
                  checked={selected.rows.has(r.key)}
                  onToggle={() => onToggleRow(r)}
                  label={r.label}
                  sub={r.sub}
                  tag={r.object_type}
                />
              ))}
            </GroupBlock>
          )
        )}
        {filteredRows.length === 0 && filteredSessions.length === 0 && (
          <div className="py-8 text-center text-[12.5px] text-muted">
            {search ? "No matches." : "This stash is empty."}
          </div>
        )}
      </div>

      <div className="border-t border-border-subtle px-5 py-3">
        <div className="mb-2 grid grid-cols-2 gap-3 text-[12px]">
          <label className="flex flex-col gap-1">
            <span className="font-medium text-foreground">Title</span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={placeholderTitle || "Untitled share"}
              className="rounded-md border border-border bg-surface px-2 py-1.5"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-medium text-foreground">Who can open</span>
            <select
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as Visibility)}
              className="rounded-md border border-border bg-surface px-2 py-1.5"
            >
              <option value="link">Anyone with the link</option>
              <option value="public">Public on the web</option>
            </select>
          </label>
        </div>

        {error && (
          <div className="mb-2 rounded-md border border-red-300/40 bg-red-500/10 px-3 py-1.5 text-[12px] text-red-400">
            {error}
          </div>
        )}

        <div className="flex items-center justify-between gap-2">
          <span className="text-[12px] text-muted">
            {total === 0
              ? "Pick at least one thing to share."
              : `${total} item${total === 1 ? "" : "s"} selected`}
          </span>
          <button
            onClick={onSubmit}
            disabled={submitting || total === 0}
            className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[13px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-40"
          >
            {submitting ? "Creating…" : "Create share link"}
          </button>
        </div>
      </div>
    </>
  );
}

function ManageTab(props: {
  views: StashView[];
  onDelete: (viewId: string) => void;
  copiedSlug: string | null;
  setCopiedSlug: (s: string | null) => void;
  error: string;
}) {
  const { views, onDelete, copiedSlug, setCopiedSlug, error } = props;
  if (views.length === 0) {
    return (
      <div className="px-5 py-10 text-center text-[12.5px] text-muted">
        No share links yet. Use the New share tab to create one.
      </div>
    );
  }
  return (
    <div className="scroll-thin flex-1 overflow-y-auto px-5 py-3">
      {error && (
        <div className="mb-3 rounded-md border border-red-300/40 bg-red-500/10 px-3 py-1.5 text-[12px] text-red-400">
          {error}
        </div>
      )}
      <ul className="flex flex-col gap-2">
        {views.map((v) => {
          const url = absoluteUrl(`/v/${v.slug}`);
          const isCopied = copiedSlug === v.slug;
          return (
            <li
              key={v.id}
              className="rounded-lg border border-border-subtle bg-surface px-3 py-2.5"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-foreground">
                    {v.title}
                  </div>
                  <div className="mt-0.5 text-[11px] text-muted">
                    {v.items.length} item{v.items.length === 1 ? "" : "s"} ·{" "}
                    {v.is_public ? "Public" : "Anyone with the link"} ·{" "}
                    {v.view_count} view{v.view_count === 1 ? "" : "s"}
                  </div>
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 block truncate font-mono text-[11px] text-[var(--color-brand-700)] hover:underline"
                  >
                    {url}
                  </a>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <button
                    onClick={async () => {
                      await navigator.clipboard.writeText(url).catch(() => {});
                      setCopiedSlug(v.slug);
                      setTimeout(() => setCopiedSlug(null), 1200);
                    }}
                    className="rounded-md border border-border-subtle px-2 py-1 text-[11px] hover:border-brand hover:text-brand"
                  >
                    {isCopied ? "Copied" : "Copy"}
                  </button>
                  <button
                    onClick={() => onDelete(v.id)}
                    className="rounded-md border border-border-subtle px-2 py-1 text-[11px] text-muted hover:border-red-400 hover:text-red-400"
                  >
                    Revoke
                  </button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function GroupBlock({
  title,
  count,
  collapsed,
  onToggleCollapse,
  allSelected,
  onToggleSelectAll,
  children,
}: {
  title: GroupKey;
  count: number;
  collapsed: boolean;
  onToggleCollapse: () => void;
  allSelected: boolean;
  onToggleSelectAll: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-3">
      <div className="mb-1 flex items-center justify-between gap-2">
        <button
          onClick={onToggleCollapse}
          className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted hover:text-foreground"
        >
          <span className="inline-block w-2 text-center">{collapsed ? "▸" : "▾"}</span>
          {title}
          <span className="font-mono normal-case text-muted">· {count}</span>
        </button>
        <button
          onClick={onToggleSelectAll}
          className="text-[10.5px] text-muted hover:text-foreground"
        >
          {allSelected ? "Clear" : "Select all"}
        </button>
      </div>
      {!collapsed && <div className="flex flex-col">{children}</div>}
    </div>
  );
}

function TriCheckbox({
  checked,
  indeterminate,
  onChange,
  label,
}: {
  checked: boolean;
  indeterminate: boolean;
  onChange: () => void;
  label: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <label className="flex cursor-pointer items-center gap-2 text-[12px] text-foreground">
      <input
        ref={ref}
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="h-3.5 w-3.5 accent-[var(--color-brand-600)]"
      />
      <span>{label}</span>
    </label>
  );
}

function Row({
  checked,
  onToggle,
  label,
  sub,
  tag,
}: {
  checked: boolean;
  onToggle: () => void;
  label: string;
  sub: string;
  tag: string;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-1.5 text-[13px] hover:bg-raised">
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="h-3.5 w-3.5 accent-[var(--color-brand-600)]"
      />
      <span className="min-w-0 flex-1 truncate text-foreground">{label}</span>
      <span className="shrink-0 text-[11px] text-muted">{sub}</span>
      <span className="shrink-0 font-mono text-[9px] uppercase tracking-wider text-muted">
        {tag}
      </span>
    </label>
  );
}

function buildInitialSelection(initial: ViewItemSpec[] | undefined): SelectedState {
  if (!initial?.length) return EMPTY_SELECTED;
  const rows = new Map<string, SelectableRow>();
  for (const item of initial) {
    if (
      item.object_type !== "folder" &&
      item.object_type !== "page" &&
      item.object_type !== "file" &&
      item.object_type !== "table"
    ) {
      continue;
    }
    const key = `${item.object_type}:${item.object_id}`;
    rows.set(key, {
      key,
      object_type: item.object_type,
      object_id: item.object_id,
      label: item.label_override || titleCase(item.object_type),
      sub: "",
      group: groupFor(item.object_type),
    });
  }
  return { rows, sessions: new Map() };
}

function buildRows(spine: StashSpine | null): SelectableRow[] {
  if (!spine) return [];
  const folders = spine.wiki.folders.map<SelectableRow>((f) => ({
    key: `folder:${f.id}`,
    object_type: "folder",
    object_id: f.id,
    label: f.name,
    sub: [
      f.page_count ? `${f.page_count} page${f.page_count === 1 ? "" : "s"}` : null,
      f.file_count ? `${f.file_count} file${f.file_count === 1 ? "" : "s"}` : null,
    ]
      .filter(Boolean)
      .join(" · ") || "Empty",
    group: "Folders",
  }));
  const pages = spine.wiki.pages.map<SelectableRow>((p) => ({
    key: `page:${p.id}`,
    object_type: "page",
    object_id: p.id,
    label: p.name.replace(/\.md$/, ""),
    sub: "",
    group: "Pages",
  }));
  const files: SelectableRow[] = [];
  const tables: SelectableRow[] = [];
  for (const f of spine.wiki.files) {
    // CSV-backed files double as tables — surface them as "Tables" so the
    // user shares the structured view rather than the raw blob.
    if (f.linked_table_id) {
      tables.push({
        key: `table:${f.linked_table_id}`,
        object_type: "table",
        object_id: f.linked_table_id,
        label: f.name,
        sub: "table",
        group: "Tables",
      });
    } else {
      files.push({
        key: `file:${f.id}`,
        object_type: "file",
        object_id: f.id,
        label: f.name,
        sub: f.content_type || "file",
        group: "Files",
      });
    }
  }
  return [...folders, ...pages, ...files, ...tables];
}

function buildSessions(spine: StashSpine | null): SessionRow[] {
  if (!spine) return [];
  return spine.sessions.map((s) => ({
    key: `session:${s.session_id}`,
    session_id: s.session_id,
    label: s.title || `#${s.session_id.slice(0, 12)}`,
    sub: s.agent_name,
  }));
}

function filterByLabel<T extends { label: string; sub: string }>(
  rows: T[],
  search: string
): T[] {
  const q = search.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter(
    (r) => r.label.toLowerCase().includes(q) || r.sub.toLowerCase().includes(q)
  );
}

function groupFor(t: SelectableRow["object_type"]): RowGroup {
  if (t === "folder") return "Folders";
  if (t === "page") return "Pages";
  if (t === "table") return "Tables";
  return "Files";
}

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function absoluteUrl(path: string): string {
  if (typeof window === "undefined") return path;
  return `${window.location.origin}${path}`;
}
