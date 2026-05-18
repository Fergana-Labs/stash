"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createStash,
  publishStash,
  getWorkspaceSidebar,
  type WorkspaceSidebar,
  type StashItemSpec,
} from "../../lib/api";
import { useShareModal } from "../../lib/shareModalContext";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import CustomSelect from "../CustomSelect";

type StashAccess = "workspace" | "private" | "public";

type RowGroup = "Folders" | "Pages" | "Files" | "Tables";
type GroupKey = "Sessions" | RowGroup;

const ROW_GROUP_ORDER: RowGroup[] = ["Folders", "Pages", "Files", "Tables"];

const STASH_ACCESS_OPTIONS = [
  { value: "workspace", label: "Everyone in this workspace" },
  { value: "private", label: "Only invited people" },
  { value: "public", label: "Public on the web" },
];

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
  object_id: string;
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
  const { open, workspaceId, workspaceName, initial } = state;

  const [spine, setSpine] = useState<WorkspaceSidebar | null>(null);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<SelectedState>(EMPTY_SELECTED);
  const [title, setTitle] = useState("");
  const [access, setAccess] = useState<StashAccess>("workspace");
  const [shareToDiscover, setShareToDiscover] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEscapeKey(open, close);

  const refresh = useCallback(async () => {
    if (!workspaceId) return;
    setSpine(await getWorkspaceSidebar(workspaceId));
  }, [workspaceId]);

  useEffect(() => {
    if (!open) return;
    setSearch("");
    setError("");
    setTitle("");
    setAccess("workspace");
    setShareToDiscover(false);
    setSelected(buildInitialSelection(initial, null));
    refresh();
  }, [open, initial, refresh]);

  useEffect(() => {
    if (!open || !spine || !initial?.some((item) => item.object_type === "session")) return;

    setSelected((current) => resolveInitialSessions(current, initial, spine));
  }, [open, initial, spine]);

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
    if (!workspaceId || total === 0) return;
    setSubmitting(true);
    setError("");
    try {
      const items: StashItemSpec[] = [];
      let pos = 0;
      for (const row of selected.rows.values()) {
        items.push({
          object_type: row.object_type,
          object_id: row.object_id,
          position: pos++,
        });
      }
      for (const sess of selected.sessions.values()) {
        items.push({
          object_type: "session",
          object_id: sess.object_id,
          position: pos++,
          label_override: sess.label,
        });
      }
      const finalTitle = title.trim() || defaultTitle;
      const stash =
        access === "public"
          ? (await publishStash(workspaceId, finalTitle, items, {
              discoverable: shareToDiscover,
            })).stash
          : await createStash(workspaceId, finalTitle, items, { access });
      if (stash.access === "public") {
        await navigator.clipboard.writeText(absoluteUrl(`/stashes/${stash.slug}`)).catch(() => {});
      }
      setSelected(EMPTY_SELECTED);
      setTitle("");
      setShareToDiscover(false);
      bumpVersion();
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create share");
    } finally {
      setSubmitting(false);
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
          <h2 className="font-display text-[15px] font-semibold text-foreground">
            {modalTitle(initial, workspaceName)}
          </h2>
          <button onClick={close} className="text-muted hover:text-foreground" aria-label="Close">
            ✕
          </button>
        </div>

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
          access={access}
          setAccess={(next) => {
            setAccess(next);
            if (next !== "public") setShareToDiscover(false);
          }}
          shareToDiscover={shareToDiscover}
          setShareToDiscover={setShareToDiscover}
          submitting={submitting}
          onSubmit={onSubmit}
          total={total}
          error={error}
        />
      </div>
    </div>
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
  access: StashAccess;
  setAccess: (v: StashAccess) => void;
  shareToDiscover: boolean;
  setShareToDiscover: (v: boolean) => void;
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
    access,
    setAccess,
    shareToDiscover,
    setShareToDiscover,
    submitting,
    onSubmit,
    total,
    error,
  } = props;

  // Default: every group collapsed. Users expand the groups they care about
  // instead of scrolling past everything at once.
  const [collapsed, setCollapsed] = useState<Set<GroupKey>>(
    () => new Set<GroupKey>(["Sessions", "Folders", "Pages", "Files", "Tables"])
  );
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
                kind="session"
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
                  kind={r.object_type}
                />
              ))}
            </GroupBlock>
          )
        )}
        {filteredRows.length === 0 && filteredSessions.length === 0 && (
          <div className="py-8 text-center text-[12.5px] text-muted">
            {search ? "No matches." : "This workspace is empty."}
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
              placeholder={placeholderTitle || "Untitled Stash"}
              className="rounded-md border border-border bg-surface px-2 py-1.5"
            />
          </label>
          <div className="flex flex-col gap-1">
            <span className="font-medium text-foreground">Stash access</span>
            <CustomSelect
              value={access}
              options={STASH_ACCESS_OPTIONS}
              onChange={(next) => setAccess(next as StashAccess)}
              ariaLabel="Stash access"
              className="w-full rounded-md border border-border bg-surface px-2 py-1.5"
              menuClassName="text-[12px]"
            />
          </div>
        </div>

        {access === "public" && (
          <label className="mb-2 flex items-start gap-2 rounded-md border border-border-subtle bg-surface px-3 py-2 text-[12px]">
            <input
              type="checkbox"
              checked={shareToDiscover}
              onChange={(e) => setShareToDiscover(e.target.checked)}
              className="mt-0.5"
            />
            <span className="min-w-0">
              <span className="block font-medium text-foreground">Share to Discover</span>
              <span className="block text-muted">
                List this public Stash in the catalog for anyone to browse.
              </span>
            </span>
          </label>
        )}

        {error && (
          <div className="mb-2 rounded-md border border-red-300/40 bg-red-500/10 px-3 py-1.5 text-[12px] text-red-400">
            {error}
          </div>
        )}

        <div className="flex items-center justify-between gap-2">
          <span className="text-[12px] text-muted">
            {total === 0
              ? "Pick at least one thing to include."
              : `${total} item${total === 1 ? "" : "s"} selected`}
          </span>
          <button
            onClick={onSubmit}
            disabled={submitting || total === 0}
            className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[13px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-40"
          >
            {submitting ? "Creating…" : "Create Stash"}
          </button>
        </div>
      </div>
    </>
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
  kind,
}: {
  checked: boolean;
  onToggle: () => void;
  label: string;
  sub: string;
  kind: string;
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
        {kind}
      </span>
    </label>
  );
}

function buildInitialSelection(
  initial: StashItemSpec[] | undefined,
  spine: WorkspaceSidebar | null
): SelectedState {
  if (!initial?.length) return EMPTY_SELECTED;
  const rows = new Map<string, SelectableRow>();
  const sessions = new Map<string, SessionRow>();
  for (const item of initial) {
    if (item.object_type === "session") {
      const session = sessionRowFromInitial(item, spine);
      if (session) sessions.set(session.key, session);
      continue;
    }

    if (!isSelectableRowType(item.object_type)) continue;

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
  return { rows, sessions };
}

function isSelectableRowType(
  objectType: StashItemSpec["object_type"]
): objectType is SelectableRow["object_type"] {
  return (
    objectType === "folder" ||
    objectType === "page" ||
    objectType === "file" ||
    objectType === "table"
  );
}

function sessionRowFromInitial(
  item: StashItemSpec,
  spine: WorkspaceSidebar | null
): SessionRow | null {
  const match = spine?.sessions.find(
    (session) => session.id === item.object_id || session.session_id === item.object_id
  );

  if (match?.id) {
    return {
      key: `session:${match.id}`,
      object_id: match.id,
      session_id: match.session_id,
      label: match.title || item.label_override || `#${match.session_id.slice(0, 12)}`,
      sub: match.agent_name,
    };
  }

  return {
    key: `session:${item.object_id}`,
    object_id: item.object_id,
    session_id: item.object_id,
    label: item.label_override || `#${item.object_id.slice(0, 12)}`,
    sub: "",
  };
}

function resolveInitialSessions(
  current: SelectedState,
  initial: StashItemSpec[],
  spine: WorkspaceSidebar
): SelectedState {
  const resolved = buildInitialSelection(initial, spine);
  if (resolved.sessions.size === 0) return current;

  const sessions = new Map(current.sessions);
  for (const initialSession of buildInitialSelection(initial, null).sessions.values()) {
    const resolvedSession = Array.from(resolved.sessions.values()).find(
      (session) => session.session_id === initialSession.session_id
    );
    if (!resolvedSession) continue;
    sessions.delete(initialSession.key);
    sessions.set(resolvedSession.key, resolvedSession);
  }

  return { rows: current.rows, sessions };
}

function buildRows(spine: WorkspaceSidebar | null): SelectableRow[] {
  if (!spine) return [];
  const tree = spine.files;
  const folders = tree.folders.map<SelectableRow>((f) => ({
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
  const pages = tree.pages.map<SelectableRow>((p) => ({
    key: `page:${p.id}`,
    object_type: "page",
    object_id: p.id,
    label: p.name.replace(/\.md$/, ""),
    sub: "",
    group: "Pages",
  }));
  const files: SelectableRow[] = [];
  const tables: SelectableRow[] = [];
  for (const f of tree.files) {
    // CSV-backed files double as tables — surface them as "Tables" so the
    // user shares the table Stash rather than the raw blob.
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

function buildSessions(spine: WorkspaceSidebar | null): SessionRow[] {
  if (!spine) return [];
  return spine.sessions
    .filter((s) => s.id)
    .map((s) => ({
      key: `session:${s.id}`,
      object_id: s.id as string,
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

function modalTitle(initial: StashItemSpec[] | undefined, workspaceName: string | undefined) {
  if (!initial?.length) return `Create Stash from ${workspaceName || "workspace"}`;
  if (initial.length > 1) return "Share as Stash";

  const type = initial[0].object_type;
  if (type === "page") return "Share page as Stash";
  if (type === "session") return "Share session as Stash";
  if (type === "folder") return "Share folder as Stash";
  if (type === "file") return "Share file as Stash";
  if (type === "table") return "Share table as Stash";
  return "Share as Stash";
}
