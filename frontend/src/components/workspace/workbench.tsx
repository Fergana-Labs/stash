"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { nanoid } from "nanoid";
import { X, SplitSquareHorizontal, PanelRightClose, Plus, Bot, Plug, FileText } from "lucide-react";
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { createPage } from "@/lib/api";
import { useWorkspace, type WorkbenchTab } from "@/lib/workspace-store";
import { ShellChromeScope, useShellChromeValue } from "@/components/ShellChromeContext";
import { urlForTab, tabFromPath } from "@/lib/workspace-routes";
import { PageIcon, FileIcon, TableIcon, SessionsIcon, SkillIcon, FolderIcon } from "@/components/SkillIcons";
import TabBody from "./tab-body";

const TAB_DND = "application/x-wb-tab";

function TabIcon({ kind }: { kind: WorkbenchTab["kind"] }) {
  const cls = "text-[13px]";
  if (kind === "page") return <PageIcon className={cls} />;
  if (kind === "file") return <FileIcon className={cls} />;
  if (kind === "table") return <TableIcon className={cls} />;
  if (kind === "folder") return <FolderIcon className={cls} />;
  if (kind === "session" || kind === "sessions-home") return <SessionsIcon className={cls} />;
  if (kind === "agent") return <Bot className="h-[13px] w-[13px]" />;
  if (kind === "tool") return <Plug className="h-[13px] w-[13px]" />;
  return <SkillIcon className={cls} />;
}

/** The "+" new-tab menu in the tab strip — create a page or start a chat. */
function NewTabMenu() {
  const router = useRouter();
  const openTab = useWorkspace((s) => s.openTab);

  async function newPage() {
    const page = await createPage("Untitled", null, "");
    openTab("page", page.id, page.name || "Untitled");
    router.replace(urlForTab({ kind: "page", refId: page.id }));
  }
  function newChat() {
    const id = `new-${nanoid(5)}`;
    openTab("agent", id, "New Chat");
    router.replace(urlForTab({ kind: "agent", refId: id }));
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex h-9 w-9 items-center justify-center text-muted-foreground hover:bg-raised hover:text-foreground" title="New tab">
          <Plus className="h-4 w-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={newPage}>
          <FileText className="h-4 w-4" /> New page
        </DropdownMenuItem>
        <DropdownMenuItem onClick={newChat}>
          <Bot className="h-4 w-4" /> New chat
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** One pane of the workbench: a tab strip + the active tab's body. `pane` is 0
 *  (left) or 1 (right, only present when split). */
function TabPane({ pane }: { pane: 0 | 1 }) {
  const router = useRouter();
  const tabs = useWorkspace((s) => s.tabs);
  const paneOf = useWorkspace((s) => s.paneOf);
  const activeTabId = useWorkspace((s) => s.activeTabId);
  const activeTab1 = useWorkspace((s) => s.activeTab1);
  const split = useWorkspace((s) => s.split);
  const setActiveTab = useWorkspace((s) => s.setActiveTab);
  const closeTab = useWorkspace((s) => s.closeTab);
  const splitTab = useWorkspace((s) => s.splitTab);
  const moveTabToPane = useWorkspace((s) => s.moveTabToPane);
  const setFocusedPane = useWorkspace((s) => s.setFocusedPane);

  const paneTabs = tabs.filter((t) => (paneOf[t.id] ?? 0) === pane);
  const activeId = pane === 0 ? activeTabId : activeTab1;
  const { shareAction } = useShellChromeValue(activeId ?? undefined);

  function focus(tab: WorkbenchTab) {
    setActiveTab(tab.id);
    router.replace(urlForTab(tab));
  }

  function onDrop(e: React.DragEvent) {
    const id = e.dataTransfer.getData(TAB_DND);
    if (id) moveTabToPane(id, pane);
  }

  return (
    <div
      className="flex min-h-0 min-w-0 flex-1 flex-col bg-base"
      onMouseDown={() => setFocusedPane(pane)}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
    >
      <div className="flex h-9 shrink-0 items-stretch border-b border-border bg-surface">
        <div className="flex min-w-0 flex-1 items-stretch overflow-x-auto">
          {paneTabs.map((tab) => {
            const active = tab.id === activeId;
            return (
              <div
                key={tab.id}
                draggable
                onDragStart={(e) => e.dataTransfer.setData(TAB_DND, tab.id)}
                onClick={() => focus(tab)}
                className={cn(
                  "group flex max-w-[200px] shrink-0 cursor-pointer items-center gap-1.5 border-r border-border px-3 text-[13px]",
                  active ? "bg-base text-foreground" : "text-muted-foreground hover:bg-base/60",
                )}
                title={tab.title}
              >
                <TabIcon kind={tab.kind} />
                <span className="min-w-0 flex-1 truncate">{tab.title}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                  }}
                  className="rounded p-0.5 opacity-0 hover:bg-raised group-hover:opacity-100"
                  aria-label="Close tab"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            );
          })}
        </div>
        <div className="flex shrink-0 items-center">
          {pane === 0 && <NewTabMenu />}
          {pane === 0 && !split && activeTabId && (
            <button
              onClick={() => splitTab(activeTabId)}
              className="flex h-9 w-9 items-center justify-center text-muted-foreground hover:bg-raised hover:text-foreground"
              title="Split right"
            >
              <SplitSquareHorizontal className="h-4 w-4" />
            </button>
          )}
          {pane === 1 && (
            <button
              onClick={() => paneTabs.forEach((t) => moveTabToPane(t.id, 0))}
              className="flex h-9 w-9 items-center justify-center text-muted-foreground hover:bg-raised hover:text-foreground"
              title="Close split"
            >
              <PanelRightClose className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      {shareAction && (
        <div className="flex h-10 shrink-0 items-center justify-end gap-2 border-b border-border bg-base px-3">
          {shareAction}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-hidden">
        {/* Only the active tab's body is mounted — page/HTML editors portal a
            floating toolbar to <body>, which would leak from hidden tabs. A
            single container here (no nested scrollers) lets each body own its
            own scroll — nested overflow-y-auto around a contenteditable breaks
            its paint. */}
        {(() => {
          const active = paneTabs.find((t) => t.id === activeId);
          if (!active)
            return (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Open something from the explorer.
              </div>
            );
          return (
            <div key={active.id} className="h-full">
              <ShellChromeScope scopeId={active.id}>
                <TabBody tab={active} />
              </ShellChromeScope>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

/**
 * The tab workbench. Tabs live in the zustand store; the URL always reflects the
 * focused tab (so deep-links/sharing work), and navigating to a content route
 * (deep link or explorer click) opens/focuses its tab here.
 */
export default function Workbench() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const split = useWorkspace((s) => s.split);
  const openTab = useWorkspace((s) => s.openTab);
  const setActiveTab = useWorkspace((s) => s.setActiveTab);

  // URL → tab: opening/focusing happens off the pathname only (never off `tabs`),
  // so this can't loop with the imperative router.replace on tab clicks.
  useEffect(() => {
    const match = pathname === "/sessions" && searchParams.get("workspace") === "1"
      ? { kind: "sessions-home" as const, refId: "sessions" }
      : tabFromPath(pathname);
    if (!match) return;
    const existing = useWorkspace.getState().tabs.find((t) => t.kind === match.kind && t.refId === match.refId);
    if (existing) setActiveTab(existing.id);
    else openTab(match.kind, match.refId, match.kind === "sessions-home" ? "Sessions" : match.refId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, searchParams]);

  if (!split) return <TabPane pane={0} />;
  return (
    <ResizablePanelGroup orientation="horizontal">
      <ResizablePanel defaultSize={50} minSize={25}>
        <TabPane pane={0} />
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel defaultSize={50} minSize={25}>
        <TabPane pane={1} />
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
