"use client";

import { type DragEvent, useCallback, useEffect, useRef, useState } from "react";

import IntegrationCard from "@/components/integrations/IntegrationCard";
import DriveImportDialog from "@/components/import/DriveImportDialog";
import GitImportDialog from "@/components/import/GitImportDialog";
import NotionImportDialog from "@/components/import/NotionImportDialog";
import { createFolder, uploadFileOrPage } from "@/lib/api";
import { IntegrationStatus, listIntegrations } from "@/lib/integrations";
import type { MigrantSource, StepCtx } from "@/lib/onboarding/paths";

function returnToForSource(source: MigrantSource): string {
  // OAuth callback redirects here. Must carry source through, otherwise the
  // step boots into "Pick a source first."
  return `/onboarding?path=migrant&step=2&source=${source}`;
}

export default function MigrantImportStep(ctx: StepCtx) {
  const { source, workspaceId, setCanContinue } = ctx;

  // Continue stays disabled until the user has dispatched an import (or
  // finished a vault upload). The wizard resets canContinue=true on each
  // step transition; we re-disable here as long as no import has fired.
  useEffect(() => {
    setCanContinue(false);
  }, [setCanContinue]);

  function markImported() {
    setCanContinue(true);
  }

  if (!source) {
    return (
      <div className="text-sm text-muted">
        Pick a source first — go back to the previous step.
      </div>
    );
  }

  if (source === "obsidian")
    return (
      <ObsidianBlock workspaceId={workspaceId} onUploaded={markImported} />
    );
  return (
    <ProviderBlock
      source={source}
      workspaceId={workspaceId}
      onDispatched={markImported}
    />
  );
}

type ProviderSource = "notion" | "github" | "drive";

const PROVIDER_COPY: Record<
  ProviderSource,
  { heading: string; subhead: string; integrationKey: string }
> = {
  notion: {
    heading: "Bring your Notion in",
    subhead: "Connect Notion, then pick what to import.",
    integrationKey: "notion",
  },
  github: {
    heading: "Bring your repo in",
    subhead:
      "Connect GitHub, then pick a repo. Everything's searchable and editable.",
    integrationKey: "github",
  },
  drive: {
    heading: "Bring your Drive in",
    subhead:
      "Connect Google, then pick what to bring over. Docs and Sheets included.",
    integrationKey: "google",
  },
};

function ProviderBlock({
  source,
  workspaceId,
  onDispatched,
}: {
  source: ProviderSource;
  workspaceId: string | null;
  onDispatched: () => void;
}) {
  const [providers, setProviders] = useState<IntegrationStatus[] | null>(null);
  const [showDialog, setShowDialog] = useState(false);
  const [dispatched, setDispatched] = useState(false);
  const returnTo = returnToForSource(source);

  const { heading, subhead, integrationKey } = PROVIDER_COPY[source];

  const refresh = useCallback(async () => {
    const r = await listIntegrations();
    setProviders(r.providers);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Re-fetch integrations when the URL carries a fresh OAuth callback.
  // URL cleanup (stripping ?connected=, writing ?source=) is handled at
  // the page level — we just need to know to refresh.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected")) void refresh();
  }, [refresh]);

  const provider = providers?.find((p) => p.provider === integrationKey);
  const isConnected = provider?.connected ?? false;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          {heading}
        </h1>
        <p className="text-sm text-dim max-w-md">{subhead}</p>
      </div>

      {provider && (
        <IntegrationCard status={provider} onChanged={refresh} returnTo={returnTo} />
      )}

      {isConnected && workspaceId && !dispatched && (
        <button
          type="button"
          onClick={() => setShowDialog(true)}
          className="rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover"
        >
          Pick what to import →
        </button>
      )}

      {dispatched && (
        <div className="rounded-xl border border-brand bg-brand/5 px-4 py-3 flex items-start gap-3">
          <span
            className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand text-white text-[10px] font-bold"
            aria-hidden
          >
            ✓
          </span>
          <div className="text-[12.5px] text-foreground leading-relaxed">
            Your import is running in the background. Continue when
            you&rsquo;re ready — it&rsquo;ll keep going.
          </div>
        </div>
      )}

      {showDialog && workspaceId && source === "notion" && (
        <NotionImportDialog
          workspaceId={workspaceId}
          onDispatched={() => {
            setShowDialog(false);
            setDispatched(true);
            onDispatched();
          }}
          onClose={() => setShowDialog(false)}
        />
      )}
      {showDialog && workspaceId && source === "github" && (
        <GitImportDialog
          workspaceId={workspaceId}
          onDispatched={() => {
            setShowDialog(false);
            setDispatched(true);
            onDispatched();
          }}
          onClose={() => setShowDialog(false)}
        />
      )}
      {showDialog && workspaceId && source === "drive" && (
        <DriveImportDialog
          workspaceId={workspaceId}
          onDispatched={() => {
            setShowDialog(false);
            setDispatched(true);
            onDispatched();
          }}
          onClose={() => setShowDialog(false)}
        />
      )}
    </div>
  );
}

function ObsidianBlock({
  workspaceId,
  onUploaded,
}: {
  workspaceId: string | null;
  onUploaded: () => void;
}) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Drop your vault
        </h1>
        <p className="text-sm text-dim max-w-md">
          Drag your Obsidian vault folder onto the drop zone, or click to
          pick it. Folder structure is preserved; every <code>.md</code>{" "}
          becomes a collaboratively-edited note.
        </p>
      </div>

      {workspaceId && (
        <VaultDropZone workspaceId={workspaceId} onUploaded={onUploaded} />
      )}

      <div className="rounded-xl border border-border-subtle bg-background/40 p-4 space-y-2 text-[12px] text-muted leading-relaxed">
        <div className="font-medium text-foreground">
          Don&rsquo;t know where your vault is?
        </div>
        <ul className="list-disc pl-5 space-y-1">
          <li>
            In Obsidian: <strong>File</strong> menu → <strong>Show in
            system explorer</strong> (or right-click any note in the
            sidebar → <strong>Reveal in Finder/Explorer</strong>) opens
            the vault folder.
          </li>
          <li>
            Common default locations:{" "}
            <code>~/Documents/</code>,{" "}
            <code>~/iCloud Drive/Obsidian/</code>, or{" "}
            <code>~/Obsidian/</code>.
          </li>
          <li>
            The vault is the folder containing your{" "}
            <code>.md</code> notes — drop that whole folder.
          </li>
        </ul>
      </div>
    </div>
  );
}

// Folder-only drop zone for the Obsidian vault import. Drag-or-click,
// recursive walk via webkitGetAsEntry (drop) or webkitRelativePath
// (browse), parents-first folder creation, files routed to
// uploadFileOrPage which makes .md/.html into pages and lands others
// in Files.
type VaultStatus =
  | { kind: "idle" }
  | { kind: "busy"; message: string }
  | { kind: "done"; message: string }
  | { kind: "error"; message: string };

function VaultDropZone({
  workspaceId,
  onUploaded,
}: {
  workspaceId: string;
  onUploaded: () => void;
}) {
  const [dragActive, setDragActive] = useState(false);
  const [status, setStatus] = useState<VaultStatus>({ kind: "idle" });
  const folderInputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);

  async function readAllEntries(reader: FileSystemDirectoryReader) {
    const all: FileSystemEntry[] = [];
    for (;;) {
      const batch: FileSystemEntry[] = await new Promise((resolve, reject) =>
        reader.readEntries(resolve, reject),
      );
      if (!batch.length) break;
      all.push(...batch);
    }
    return all;
  }

  async function flattenEntries(
    entries: FileSystemEntry[],
    prefix: string[] = [],
  ): Promise<{ file: File; path: string[] }[]> {
    const out: { file: File; path: string[] }[] = [];
    for (const entry of entries) {
      if (entry.isFile) {
        const file = await new Promise<File>((resolve, reject) =>
          (entry as FileSystemFileEntry).file(resolve, reject),
        );
        out.push({ file, path: prefix });
      } else if (entry.isDirectory) {
        // Skip Obsidian's internal config / plugin cruft.
        if (entry.name === ".obsidian" || entry.name.startsWith(".")) continue;
        const reader = (entry as FileSystemDirectoryEntry).createReader();
        const children = await readAllEntries(reader);
        const nested = await flattenEntries(children, [...prefix, entry.name]);
        out.push(...nested);
      }
    }
    return out;
  }

  async function uploadWithPaths(items: { file: File; path: string[] }[]) {
    if (!items.length) return;
    setStatus({ kind: "busy", message: `Uploading ${items.length} files…` });

    const folderCache = new Map<string, string>();
    folderCache.set("", "");

    async function ensureFolder(path: string[]): Promise<string | null> {
      if (path.length === 0) return null;
      const key = path.join("/");
      const cached = folderCache.get(key);
      if (cached !== undefined) return cached || null;
      const parentId = await ensureFolder(path.slice(0, -1));
      const folder = await createFolder(
        workspaceId,
        path[path.length - 1],
        parentId,
      );
      folderCache.set(key, folder.id);
      return folder.id;
    }

    let uploaded = 0;
    try {
      for (const { file, path } of items) {
        const folderId = await ensureFolder(path);
        await uploadFileOrPage(workspaceId, file, folderId);
        uploaded += 1;
      }
    } catch (e) {
      setStatus({
        kind: "error",
        message: e instanceof Error ? e.message : "Upload failed",
      });
      return;
    }
    setStatus({
      kind: "done",
      message: `Uploaded ${uploaded} file${uploaded === 1 ? "" : "s"} from your vault.`,
    });
    if (uploaded > 0) onUploaded();
  }

  async function handleDrop(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = 0;
    setDragActive(false);
    const items = e.dataTransfer.items ? Array.from(e.dataTransfer.items) : [];
    const entries = items
      .filter((it) => it.kind === "file")
      .map((it) => it.webkitGetAsEntry?.())
      .filter((x): x is FileSystemEntry => !!x);
    if (entries.length === 0) {
      setStatus({
        kind: "error",
        message: "Drop a folder (not a single file).",
      });
      return;
    }
    const flat = await flattenEntries(entries);
    await uploadWithPaths(flat);
  }

  async function handleBrowsed(files: FileList) {
    const items: { file: File; path: string[] }[] = [];
    for (const file of Array.from(files)) {
      const rel = (file as File & { webkitRelativePath?: string })
        .webkitRelativePath;
      const parts = rel ? rel.split("/").slice(0, -1) : [];
      // Skip Obsidian internals.
      if (parts.some((p) => p === ".obsidian" || p.startsWith("."))) continue;
      items.push({ file, path: parts });
    }
    await uploadWithPaths(items);
  }

  function isFilesDrag(e: DragEvent) {
    return Array.from(e.dataTransfer.types).includes("Files");
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => folderInputRef.current?.click()}
        onDragEnter={(e) => {
          if (!isFilesDrag(e)) return;
          e.preventDefault();
          e.stopPropagation();
          dragDepth.current += 1;
          setDragActive(true);
        }}
        onDragLeave={(e) => {
          if (!isFilesDrag(e)) return;
          e.preventDefault();
          e.stopPropagation();
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragActive(false);
        }}
        onDragOver={(e) => {
          if (!isFilesDrag(e)) return;
          e.preventDefault();
          e.stopPropagation();
          e.dataTransfer.dropEffect = "copy";
        }}
        onDrop={handleDrop}
        className={`w-full flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragActive
            ? "border-brand bg-brand/10"
            : "border-border bg-background/40 hover:border-brand hover:bg-raised"
        }`}
      >
        <div className="text-[24px] leading-none" aria-hidden>
          📁
        </div>
        <div className="text-[13px] font-medium text-foreground">
          {dragActive
            ? "Release to upload your vault"
            : "Drop a vault folder, or click to browse"}
        </div>
        <div className="text-[11px] text-muted">
          <code className="text-foreground">.obsidian/</code> and other dot-
          folders are skipped automatically.
        </div>
      </button>

      <input
        ref={folderInputRef}
        type="file"
        multiple
        {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) void handleBrowsed(e.target.files);
          if (folderInputRef.current) folderInputRef.current.value = "";
        }}
      />

      {status.kind !== "idle" && (
        <p
          className={`text-[11.5px] ${
            status.kind === "error"
              ? "text-error"
              : status.kind === "done"
                ? "text-brand"
                : "text-muted"
          }`}
        >
          {status.message}
        </p>
      )}
    </div>
  );
}
