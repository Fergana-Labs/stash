"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import CustomSelect from "../../../../components/CustomSelect";
import { WorkspaceSettingsSkeleton } from "../../../../components/SkeletonStates";
import { useAuth } from "../../../../hooks/useAuth";
import {
  deleteWorkspace,
  getWorkspace,
  getWorkspaceMembers,
  kickWorkspaceMember,
  setWorkspaceMemberRole,
  updateWorkspace,
  uploadFile,
} from "../../../../lib/api";
import { resetStashNavigationCache } from "../../../../lib/stashNavigationCache";
import type { Workspace, WorkspaceMember } from "../../../../lib/types";

const MEMBER_ROLE_OPTIONS = [
  { value: "viewer", label: "Viewer" },
  { value: "editor", label: "Editor" },
  { value: "owner", label: "Admin" },
];

function roleLabel(role: string): string {
  if (role === "owner") return "admin";
  return role;
}

export default function StashSettingsPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user } = useAuth();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [error, setError] = useState("");

  useBreadcrumbs([{ label: "Settings" }], `${workspaceId}/settings`);

  const load = useCallback(async () => {
    try {
      const [ws, m] = await Promise.all([
        getWorkspace(workspaceId),
        getWorkspaceMembers(workspaceId),
      ]);
      setWorkspace(ws);
      setMembers(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings");
    }
  }, [workspaceId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  if (!user) return null;
  if (!workspace) {
    if (error) return <div className="mx-auto max-w-2xl px-8 py-12 text-muted">{error}</div>;
    return <WorkspaceSettingsSkeleton />;
  }

  const myRole = members.find((m) => m.user_id === user.id)?.role;
  const isAdmin = myRole === "owner";

  async function changeMemberRole(userId: string, role: "owner" | "editor" | "viewer") {
    await setWorkspaceMemberRole(workspaceId, userId, role);
    await load();
  }

  async function uploadAndSet(file: File, field: "cover_image_url" | "icon_url") {
    if (!workspace) return;
    const uploaded = await uploadFile(workspace.id, file);
    const updated = await updateWorkspace(workspace.id, { [field]: uploaded.url });
    setWorkspace(updated);
  }

  async function clearField(field: "cover_image_url" | "icon_url" | "color_gradient") {
    if (!workspace) return;
    const updated = await updateWorkspace(workspace.id, { [field]: null });
    setWorkspace(updated);
  }

  async function setGradient(gradient: string | null) {
    if (!workspace) return;
    const updated = await updateWorkspace(workspace.id, { color_gradient: gradient });
    setWorkspace(updated);
  }

  async function removeMember(userId: string) {
    if (!confirm("Remove this member from the workspace?")) return;
    await kickWorkspaceMember(workspaceId, userId);
    await load();
  }

  async function handleDelete() {
    if (!confirm(`Delete "${workspace!.name}"? This cannot be undone.`)) return;
    await deleteWorkspace(workspace!.id);
    resetStashNavigationCache();
    router.push("/");
  }

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-8 py-10">
        <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
          Settings
        </h1>
        <p className="mt-1 text-[13px] text-muted">{workspace.name}</p>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        <Section title="Members">
          <ul className="flex flex-col gap-2">
            {members.map((m) => (
              <li
                key={m.user_id}
                className="flex items-center justify-between rounded-lg border border-border bg-base px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="truncate text-[13.5px] font-medium text-foreground">
                    {m.display_name}
                  </div>
                  <div className="text-[11.5px] text-muted">@{m.name}</div>
                </div>
                <div className="flex items-center gap-2">
                  {isAdmin && m.user_id !== user.id ? (
                    <>
                      <CustomSelect
                        value={m.role}
                        options={MEMBER_ROLE_OPTIONS}
                        onChange={(next) =>
                          changeMemberRole(
                            m.user_id,
                            next as "owner" | "editor" | "viewer"
                          )
                        }
                        className="min-w-[82px] rounded border border-border bg-surface px-2 py-1 text-[12px]"
                        align="right"
                      />
                      <button
                        onClick={() => removeMember(m.user_id)}
                        className="text-[11.5px] text-red-500 hover:underline"
                      >
                        Remove
                      </button>
                    </>
                  ) : (
                    <span className="rounded bg-raised px-2 py-0.5 text-[11.5px] text-muted">
                      {roleLabel(m.role)}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Branding">
          <ImageField
            label="Banner"
            sub="Wide image rendered above the workspace header."
            url={workspace.cover_image_url ?? null}
            canEdit={isAdmin}
            onUpload={(f) => uploadAndSet(f, "cover_image_url")}
            onClear={() => clearField("cover_image_url")}
            previewClass="h-16 w-full rounded-md object-cover"
          />
          <ImageField
            label="Icon"
            sub="Square logo for the workspace hero."
            url={workspace.icon_url ?? null}
            canEdit={isAdmin}
            onUpload={(f) => uploadAndSet(f, "icon_url")}
            onClear={() => clearField("icon_url")}
            previewClass="h-12 w-12 rounded-md object-cover"
          />
          <div className="rounded-lg border border-border bg-base px-3 py-2">
            <div className="text-[13.5px] font-medium text-foreground">Color gradient</div>
            <div className="text-[11.5px] text-muted">
              Used when no banner image is set.
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {GRADIENT_PRESETS.map((g) => (
                <button
                  key={g.label}
                  onClick={() => setGradient(g.css)}
                  disabled={!isAdmin}
                  className={
                    "h-8 w-16 rounded-md border " +
                    (workspace.color_gradient === g.css
                      ? "border-foreground ring-2 ring-[var(--color-brand-300)]"
                      : "border-border")
                  }
                  style={{ backgroundImage: g.css }}
                  title={g.label}
                />
              ))}
              {workspace.color_gradient && isAdmin && (
                <button
                  onClick={() => clearField("color_gradient")}
                  className="text-[11.5px] text-muted hover:text-foreground"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
        </Section>

        {isAdmin && (
          <Section title="Danger zone">
            <button
              onClick={handleDelete}
              className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-[13px] font-medium text-red-700 hover:bg-red-100"
            >
              Delete this workspace
            </button>
          </Section>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-[12px] font-semibold uppercase tracking-wider text-muted">
        {title}
      </h2>
      <div className="mt-3 flex flex-col gap-2">{children}</div>
    </section>
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
  canEdit,
  onUpload,
  onClear,
  previewClass,
}: {
  label: string;
  sub: string;
  url: string | null;
  canEdit: boolean;
  onUpload: (f: File) => Promise<void>;
  onClear: () => Promise<void>;
  previewClass: string;
}) {
  const inputId = `upload-${label.toLowerCase()}`;
  return (
    <div className="rounded-lg border border-border bg-base px-3 py-2">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[13.5px] font-medium text-foreground">{label}</div>
          <div className="text-[11.5px] text-muted">{sub}</div>
        </div>
        {canEdit && (
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
              <button
                onClick={onClear}
                className="text-[11.5px] text-muted hover:text-foreground"
              >
                Clear
              </button>
            )}
          </div>
        )}
      </div>
      {url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className={"mt-2 " + previewClass} />
      )}
    </div>
  );
}
