"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  deleteWorkspace,
  getWorkspace,
  listMyWorkspaces,
  updateWorkspace,
  uploadFile,
} from "../../lib/api";
import { resetStashNavigationCache } from "../../lib/stashNavigationCache";
import type { Workspace } from "../../lib/types";

// The sidebar remembers the last workspace the user was in; the unified
// settings page edits that one (a user can belong to several, but only one is
// "where they are"). Falls back to their first owned workspace.
const LAST_WORKSPACE_KEY = "stash_sidebar_last_workspace";

export default function WorkspaceSection() {
  const router = useRouter();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const stored =
        typeof window !== "undefined" ? localStorage.getItem(LAST_WORKSPACE_KEY) : null;
      const id = stored || (await listMyWorkspaces()).workspaces[0]?.id;
      if (!id) return;
      setWorkspace(await getWorkspace(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load workspace");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function uploadAndSet(file: File, field: "cover_image_url" | "icon_url") {
    if (!workspace) return;
    const uploaded = await uploadFile(workspace.id, file);
    setWorkspace(await updateWorkspace(workspace.id, { [field]: uploaded.url }));
  }

  async function clearField(field: "cover_image_url" | "icon_url" | "color_gradient") {
    if (!workspace) return;
    setWorkspace(await updateWorkspace(workspace.id, { [field]: null }));
  }

  async function setGradient(gradient: string | null) {
    if (!workspace) return;
    setWorkspace(await updateWorkspace(workspace.id, { color_gradient: gradient }));
  }

  async function handleDelete() {
    if (!workspace) return;
    if (!confirm(`Delete "${workspace.name}"? This cannot be undone.`)) return;
    await deleteWorkspace(workspace.id);
    resetStashNavigationCache();
    router.push("/");
  }

  if (!workspace) {
    return error ? <p className="text-xs text-error">{error}</p> : null;
  }

  return (
    <>
      <section className="rounded-2xl border border-border bg-surface p-6 space-y-4">
        <div>
          <h2 className="text-base font-semibold text-foreground">General</h2>
          <p className="text-xs text-muted mt-0.5">
            Branding for <span className="font-medium text-foreground">{workspace.name}</span>.
          </p>
        </div>
        <ImageField
          label="Banner"
          sub="Wide image rendered above the header."
          url={workspace.cover_image_url ?? null}
          onUpload={(f) => uploadAndSet(f, "cover_image_url")}
          onClear={() => clearField("cover_image_url")}
          previewClass="h-16 w-full rounded-md object-cover"
        />
        <ImageField
          label="Icon"
          sub="Square logo for the hero."
          url={workspace.icon_url ?? null}
          onUpload={(f) => uploadAndSet(f, "icon_url")}
          onClear={() => clearField("icon_url")}
          previewClass="h-12 w-12 rounded-md object-cover"
        />
        <div className="rounded-lg border border-border bg-background px-3 py-2">
          <div className="text-[13.5px] font-medium text-foreground">Color gradient</div>
          <div className="text-[11.5px] text-muted">Used when no banner image is set.</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {GRADIENT_PRESETS.map((g) => (
              <button
                key={g.label}
                onClick={() => setGradient(g.css)}
                className={
                  "h-8 w-16 rounded-md border " +
                  (workspace.color_gradient === g.css
                    ? "border-foreground ring-2 ring-brand/30"
                    : "border-border")
                }
                style={{ backgroundImage: g.css }}
                title={g.label}
              />
            ))}
            {workspace.color_gradient && (
              <button
                onClick={() => clearField("color_gradient")}
                className="text-[11.5px] text-muted hover:text-foreground"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-error/40 bg-error/5 p-6 space-y-3">
        <div>
          <h2 className="text-base font-semibold text-foreground">Danger zone</h2>
          <p className="text-xs text-muted mt-0.5">
            Deleting this removes its pages, sessions, tables, and files. This cannot be
            undone.
          </p>
        </div>
        <button
          onClick={handleDelete}
          className="rounded-lg border border-error/60 px-3 py-2 text-sm font-medium text-error hover:bg-error/10 transition-colors"
        >
          Delete this workspace
        </button>
      </section>
    </>
  );
}

const GRADIENT_PRESETS = [
  { label: "Warm", css: "linear-gradient(to right, #fde68a, #fda4af)" },
  { label: "Sunset", css: "linear-gradient(to right, #fb923c, #db2777)" },
  { label: "Ocean", css: "linear-gradient(to right, #38bdf8, #6366f1)" },
  { label: "Forest", css: "linear-gradient(to right, #86efac, #14b8a6)" },
  { label: "Slate", css: "linear-gradient(to right, #cbd5e1, #64748b)" },
  { label: "Plum", css: "linear-gradient(to right, #c4b5fd, #ec4899)" },
];

function ImageField({
  label,
  sub,
  url,
  onUpload,
  onClear,
  previewClass,
}: {
  label: string;
  sub: string;
  url: string | null;
  onUpload: (f: File) => Promise<void>;
  onClear: () => Promise<void>;
  previewClass: string;
}) {
  const inputId = `ws-upload-${label.toLowerCase()}`;
  return (
    <div className="rounded-lg border border-border bg-background px-3 py-2">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[13.5px] font-medium text-foreground">{label}</div>
          <div className="text-[11.5px] text-muted">{sub}</div>
        </div>
        <div className="flex items-center gap-2">
          <label
            htmlFor={inputId}
            className="cursor-pointer rounded-md border border-border bg-surface px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
          >
            {url ? "Replace" : "Upload"}
          </label>
          <input
            id={inputId}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
              e.target.value = "";
            }}
          />
          {url && (
            <button onClick={onClear} className="text-[11.5px] text-muted hover:text-foreground">
              Clear
            </button>
          )}
        </div>
      </div>
      {url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className={"mt-2 " + previewClass} />
      )}
    </div>
  );
}
