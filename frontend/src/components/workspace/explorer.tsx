"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { nanoid } from "nanoid";
import { Bot, ChevronRight, File, Folder, Loader2, MessagesSquare, GraduationCap, Monitor, Plus, Settings, FolderTree, Brain, Plug, Sparkles, SquareTerminal } from "lucide-react";
import { toast } from "sonner";
import { listMySessions, listSessionFolders, createSessionFolder, listSkills, listSources, createFolder, createPage, machineFsList, listAgents, createAgent, type Agent as AgentRow, type MachineEntry, type SessionSummary, type Source } from "@/lib/api";
import { useMemoryFolderId } from "@/lib/memory-folder";
import { SKILL_MD, skillMdTemplate } from "@/lib/localSkill";
import { requestAgentConfigView, requestCuratorRun } from "@/lib/agent-tab-view";
import { cn } from "@/lib/utils";
import { useWorkspace, type TabKind } from "@/lib/workspace-store";
import { urlForTab } from "@/lib/workspace-routes";
import { CONNECTORS, connectorIcon, providerForSourceType } from "@/components/integrations/connectors";
import { opensNewTab } from "@/lib/tab-nav";
import FilesExplorer, { type Item } from "./files-explorer";

export type ExplorerSection = "files" | "sessions" | "skills" | "agents" | "memory" | "tools" | "computer";

const SECTIONS: { key: ExplorerSection; label: string; route: string; icon: React.ReactNode }[] = [
  { key: "files", label: "Files", route: "/files", icon: <FolderTree className="h-4 w-4 text-chart-4" /> },
  { key: "skills", label: "Skills", route: "/skills", icon: <GraduationCap className="h-4 w-4 text-chart-4" /> },
  { key: "sessions", label: "Sessions", route: "/sessions", icon: <MessagesSquare className="h-4 w-4 text-chart-4" /> },
  { key: "memory", label: "Memory", route: "/memory", icon: <Brain className="h-4 w-4 text-chart-4" /> },
  { key: "tools", label: "Tools", route: "/tools", icon: <Plug className="h-4 w-4 text-chart-4" /> },
  { key: "computer", label: "VM", route: "/agents", icon: <Monitor className="h-4 w-4 text-chart-4" /> },
];
const LABEL: Record<ExplorerSection, string> = { files: "Files", skills: "Skills", sessions: "Sessions", memory: "Memory", tools: "Tools", agents: "Agents", computer: "VM" };

/** Open any item as a workbench tab and sync the URL. A plain click navigates
 *  the current tab; cmd/ctrl-click (or an explicit newTab) opens a new one. */
function useOpenTab() {
  const router = useRouter();
  const openTab = useWorkspace((s) => s.openTab);
  return (kind: TabKind, refId: string, title: string, opts?: { newTab?: boolean }) => {
    openTab(kind, refId, title, { newTab: opts?.newTab ?? opensNewTab() });
    router.replace(urlForTab({ kind, refId }));
  };
}

// `onClick` (single) is for navigation rows (Home → section). Rows without one
// open on single click (web convention); rows with both keep `onOpen` on
// double-click so navigate and open don't collide.
function LeafRow({ icon, label, onClick, onOpen, trailing }: { icon: React.ReactNode; label: string; onClick?: () => void; onOpen?: () => void; trailing?: React.ReactNode }) {
  return (
    <button onClick={onClick ?? onOpen} onDoubleClick={onClick ? onOpen : undefined} className="group flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[13px] text-sidebar-foreground hover:bg-sidebar-accent" title={label}>
      <span className="flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground">{icon}</span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {trailing}
    </button>
  );
}

function LoadingRow() {
  return <div className="flex items-center gap-2 px-3 py-2 text-[12px] text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…</div>;
}

// Tools = every integration/connector (Slack, Granola, GitHub, …), connected or
// not. Clicking opens the integrations manager to connect/configure.
function ToolsSection() {
  const open = useOpenTab();
  const [connected, setConnected] = useState<Set<string>>(new Set());
  useEffect(() => {
    listSources().then((all) => setConnected(new Set(all.map((s: Source) => providerForSourceType[s.type] ?? s.type)))).catch(() => {});
  }, []);
  return (
    <div className="py-1">
      {CONNECTORS.map((c) => (
        <LeafRow
          key={c.provider}
          icon={connectorIcon(c.provider) ?? <Plug className="h-3.5 w-3.5" />}
          label={c.label}
          trailing={
            <span className={cn("text-[10px]", connected.has(c.provider) ? "text-[var(--color-success)]" : "text-muted-foreground opacity-0 group-hover:opacity-100")}>
              {connected.has(c.provider) ? "Connected" : "Connect"}
            </span>
          }
          onOpen={() => open("tool", c.provider, c.label)}
        />
      ))}
    </div>
  );
}

// Computer = a read-through view of the agent's working folder on the user's
// cloud machine. Browsing wakes a sleeping machine; nothing here is
// synced — "Save to Stash" on an open file is the only copy path.
function ComputerSection() {
  const open = useOpenTab();
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<MachineEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setEntries(null);
    setError(null);
    machineFsList(path)
      .then((rows) => { if (!cancelled) setEntries(rows); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [path]);

  const crumbs = path ? path.split("/") : [];
  return (
    <div className="py-1">
      <LeafRow
        icon={<SquareTerminal className="h-3.5 w-3.5" />}
        label="Terminal"
        onOpen={() => open("terminal", "terminal", "Terminal")}
      />
      <div className="mx-2 my-1 border-t border-sidebar-border" />
      <div className="flex flex-wrap items-center gap-1 px-2 py-1 text-[12px] text-muted-foreground">
        <button className="hover:text-foreground" onClick={() => setPath("")}>~</button>
        {crumbs.map((c, i) => (
          <span key={i} className="flex items-center gap-1">
            <span className="text-muted-foreground/50">/</span>
            <button className="hover:text-foreground" onClick={() => setPath(crumbs.slice(0, i + 1).join("/"))}>{c}</button>
          </span>
        ))}
      </div>
      {error && <div className="px-3 py-2 text-[12px] text-muted-foreground">Waking your VM… {error.includes("502") ? "" : error}</div>}
      {!entries && !error && <LoadingRow />}
      {entries?.map((e) => (
        <LeafRow
          key={e.name}
          icon={e.dir ? <Folder className="h-3.5 w-3.5" /> : <File className="h-3.5 w-3.5" />}
          label={e.name}
          onClick={e.dir ? () => setPath(path ? `${path}/${e.name}` : e.name) : undefined}
          onOpen={e.dir ? undefined : () => {
            const filePath = path ? `${path}/${e.name}` : e.name;
            open("machine-file", filePath, e.name);
          }}
        />
      ))}
      {entries?.length === 0 && <div className="px-3 py-2 text-[12px] text-muted-foreground">Empty</div>}
    </div>
  );
}

function RootSection() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const open = useOpenTab();
  const setRailSection = useWorkspace((s) => s.setRailSection);

  function selectSection(section: ExplorerSection) {
    const params = new URLSearchParams(searchParams);
    params.set("section", section);
    setRailSection(section);
    router.replace(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="py-1">
      {SECTIONS.map((s) => (
        <LeafRow
          key={s.key}
          icon={s.icon}
          label={s.label}
          onClick={() => selectSection(s.key)}
          onOpen={s.key === "sessions" ? () => open("sessions-home", "sessions", "Sessions") : undefined}
          trailing={<ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
        />
      ))}
    </div>
  );
}

// ── Agents: named agent configs (each with New chat + settings), then chats ──
function AgentsExplorer() {
  const open = useOpenTab();
  const [agents, setAgents] = useState<AgentRow[] | null>(null);
  const [rows, setRows] = useState<SessionSummary[] | null>(null);
  const reloadAgents = useCallback(() => { listAgents().then(setAgents).catch(() => setAgents([])); }, []);
  // Recent chats here are only conversations that ran through our platform
  // agents — CLI transcripts live in the Sessions view, not here.
  useEffect(() => { reloadAgents(); listMySessions(50, undefined, 0, true).then(setRows).catch(() => setRows([])); }, [reloadAgents]);
  // Keep the list fresh when the config panel saves/deletes an agent.
  useEffect(() => {
    const onChange = () => reloadAgents();
    window.addEventListener("agents-changed", onChange);
    return () => window.removeEventListener("agents-changed", onChange);
  }, [reloadAgents]);

  async function newAgent() {
    const a = await createAgent({ name: "New agent" });
    reloadAgents();
    // A fresh agent wants configuring first — open its tab on the Config side.
    requestAgentConfigView(a.id);
    open("agent", `agent-${a.id}`, a.name, { newTab: true });
  }

  // The curator has no chat — its settings are their own tab. Every other
  // agent's settings live on the Config side of its single chat tab.
  function openSettings(a: AgentRow) {
    if (a.is_curator) {
      open("agent-config", a.id, a.name);
      return;
    }
    requestAgentConfigView(a.id);
    open("agent", `agent-${a.id}`, a.name);
  }

  return (
    <div className="flex h-full flex-col bg-sidebar">
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-sidebar-border px-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        <span>Agents</span>
        <button onClick={() => void newAgent()} className="cursor-pointer text-muted-foreground hover:text-foreground" title="New agent">
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {(agents ?? []).map((a) => (
          <div key={a.id} className="group flex items-center gap-1 rounded px-2 py-1.5 text-[13px] text-sidebar-foreground hover:bg-sidebar-accent">
            <button
              // The curator isn't a chat agent — open its config (Run now lives
              // there). Everyone else opens their persistent chat session: a
              // stable per-agent session id so the row resumes one conversation.
              onClick={() =>
                a.is_curator
                  ? open("agent-config", a.id, a.name)
                  : open("agent", `agent-${a.id}`, a.name)
              }
              className="flex min-w-0 flex-1 cursor-pointer items-center gap-1 text-left"
              title={a.is_curator ? "Open curator settings" : "Open chat"}
            >
              <Bot className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate">{a.name}</span>
            </button>
            {!a.is_curator && (
              <button onClick={() => open("agent", `new:${a.id}:${nanoid(5)}`, a.name, { newTab: true })} className="cursor-pointer text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-foreground" title="New chat">
                <Plus className="h-3.5 w-3.5" />
              </button>
            )}
            <button onClick={() => openSettings(a)} className="cursor-pointer text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-foreground" title="Settings">
              <Settings className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
        <div className="mx-2 my-1 border-t border-sidebar-border" />
        <div className="px-2 py-1 text-[10.5px] font-medium uppercase tracking-wide text-muted-foreground">Recent chats</div>
        {(rows ?? []).map((s) => (
          <LeafRow
            key={s.session_id}
            icon={<MessagesSquare className="h-3.5 w-3.5" />}
            label={s.title || s.agent_name || "Chat"}
            onOpen={() => open("agent", s.session_id, s.title || s.agent_name || "Chat")}
            // Which agent ran this chat — titles alone hide scheduled runs
            // (e.g. the Memory curator's) in a flat list.
            trailing={s.agent_name ? <span className="max-w-[90px] shrink-0 truncate text-[10.5px] text-muted-foreground/70">{s.agent_name}</span> : undefined}
          />
        ))}
      </div>
    </div>
  );
}

/** The left panel. Agents is a chat list. Every other section is shown fully
 *  (no accordion) with a breadcrumb up to Home, which lists the sections. Files
 *  and Memory are VFS file managers (breadcrumbs, context menu, drag, upload);
 *  Memory is a dedicated reserved folder, hidden from Files. */
export default function Explorer({ section }: { section: ExplorerSection }) {
  const router = useRouter();
  const open = useOpenTab();
  const [atRoot, setAtRoot] = useState(false);
  const memoryFolderId = useMemoryFolderId();
  // A rail-section change means we're back to viewing that section, not Home.
  useEffect(() => { setAtRoot(false); }, [section]);

  // Skills are VFS folders too — the Skills explorer roots at the list of skills
  // and drills into each skill folder like any other.
  const skillsRoot = useCallback(async (): Promise<Item[]> => {
    const skills = await listSkills();
    return skills.map((s) => ({ kind: "skill" as const, id: s.folder_id, name: s.name }));
  }, []);
  // A skill is a folder + SKILL.md — the Skills root's "create native item" action.
  const createSkill = useCallback(async () => {
    const folder = await createFolder("New skill", null);
    await createPage(SKILL_MD, folder.id, skillMdTemplate("New skill"));
  }, []);

  // Sessions are their own tree: session folders + loose sessions at the root,
  // sessions inside each folder. Flat (folders don't nest).
  const sessionLabel = (s: SessionSummary) => s.title || s.agent_name || "Session";
  const sessionsRoot = useCallback(async (): Promise<Item[]> => {
    const [folders, sessions] = await Promise.all([listSessionFolders(), listMySessions(100)]);
    return [
      ...folders.map((f) => ({ kind: "session-folder" as const, id: f.id, name: f.name })),
      ...sessions.filter((s) => !s.session_folder_id).map((s) => ({ kind: "session" as const, id: s.session_id, name: sessionLabel(s), ts: s.last_event_at })),
    ];
  }, []);
  const sessionsFolder = useCallback(async (folderId: string) => {
    const [folders, sessions] = await Promise.all([listSessionFolders(), listMySessions(100, folderId)]);
    const folder = folders.find((f) => f.id === folderId);
    return {
      crumbs: [{ id: folderId, name: folder?.name ?? "Folder", is_skill: false }],
      items: sessions.map((s) => ({ kind: "session" as const, id: s.session_id, name: sessionLabel(s), ts: s.last_event_at })),
    };
  }, []);
  const createSessionFolderItem = useCallback(async () => { await createSessionFolder("New folder"); }, []);

  if (section === "agents") return <AgentsExplorer />;

  // "Curate wiki": open the Memory curator's tab and start a pass immediately,
  // so the wiki can be refreshed from Memory without hunting through Agents.
  async function curateWiki() {
    const curator = (await listAgents()).find((a) => a.is_curator);
    if (!curator) {
      toast.error("No Memory curator agent found on this account.");
      return;
    }
    requestCuratorRun();
    open("agent-config", curator.id, curator.name);
  }

  // Files, Memory, Skills & Sessions are all file managers (own breadcrumb/toolbar).
  if ((section === "files" || section === "memory" || section === "skills" || section === "sessions") && !atRoot) {
    if (section === "memory" && !memoryFolderId) {
      return <div className="flex h-full flex-col bg-sidebar"><div className="flex h-9 items-center border-b border-sidebar-border px-3 text-[12px] text-muted-foreground">Home / Memory</div><LoadingRow /></div>;
    }
    const isSessions = section === "sessions";
    return (
      <div className="flex h-full flex-col bg-sidebar">
        <FilesExplorer
          key={section}
          onRoot={() => setAtRoot(true)}
          rootLabel={LABEL[section]}
          rootFolderId={section === "memory" ? memoryFolderId : null}
          hideFolderId={section === "files" ? memoryFolderId : null}
          tabSection={section === "memory" ? "memory" : undefined}
          loadRoot={section === "skills" ? skillsRoot : isSessions ? sessionsRoot : undefined}
          loadFolder={isSessions ? sessionsFolder : undefined}
          newRootItem={
            section === "skills" ? { label: "New skill", run: createSkill } :
            isSessions ? { label: "New folder", run: createSessionFolderItem } : undefined
          }
          openRootTab={isSessions ? () => open("sessions-home", "sessions", "Sessions") : undefined}
          showImport={!isSessions}
          vfsWritable={!isSessions}
          headerAction={
            section === "memory"
              ? { icon: <Sparkles className="h-4 w-4" />, label: "Curate wiki", run: () => void curateWiki() }
              : undefined
          }
          confirmMemoryWrites={section === "memory"}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-sidebar">
      {/* Breadcrumb + actions on one row (matches the Files explorer). */}
      <div className="flex h-9 shrink-0 items-center gap-1.5 border-b border-[var(--divider-color)] px-3 text-[12px]">
        <button onClick={() => setAtRoot(true)} className={cn("truncate hover:text-foreground", atRoot ? "font-medium text-foreground" : "text-muted-foreground")}>
          Home
        </button>
        {!atRoot && (
          <>
            <span className="text-muted-foreground/50">/</span>
            <button onClick={() => router.push(SECTIONS.find((s) => s.key === section)?.route ?? "/files")} className="truncate font-medium text-foreground">
              {LABEL[section]}
            </button>
          </>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {atRoot ? <RootSection /> : section === "computer" ? <ComputerSection /> : <ToolsSection />}
      </div>
    </div>
  );
}
