"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import { useAuth } from "../../../../hooks/useAuth";
import {
  deleteWorkspace,
  editStashHandoff,
  getStashHandoff,
  getWorkspace,
  getWorkspaceMembers,
  kickWorkspaceMember,
  setWorkspaceMemberRole,
  unpinStashHandoff,
  updateWorkspace,
  uploadFile,
  type StashHandoff,
} from "../../../../lib/api";
import { homeBackgroundStyle } from "../../../../lib/homeBackground";
import { resetStashNavigationCache } from "../../../../lib/stashNavigationCache";
import type { HomeBackground, Workspace, WorkspaceMember } from "../../../../lib/types";

type Visibility = "private" | "unlisted" | "public";

function inferVisibility(ws: Workspace | null): Visibility {
  if (!ws?.is_public) return "private";
  return ws.discoverable ? "public" : "unlisted";
}

export default function StashSettingsPage() {
  const params = useParams();
  const router = useRouter();
  const stashId = params.stashId as string;
  const { user } = useAuth();

  const [stash, setStash] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [handoff, setHandoff] = useState<StashHandoff | null>(null);
  const [backgroundDraft, setBackgroundDraft] = useState<HomeBackground | null>(null);
  const [savingBackground, setSavingBackground] = useState(false);
  const [backgroundError, setBackgroundError] = useState("");
  const [savingVis, setSavingVis] = useState(false);
  const [error, setError] = useState("");

  useBreadcrumbs([{ label: "Settings" }], `${stashId}/settings`);

  const load = useCallback(async () => {
    try {
      const [ws, m, h] = await Promise.all([
        getWorkspace(stashId),
        getWorkspaceMembers(stashId),
        getStashHandoff(stashId).catch(() => null),
      ]);
      setStash(ws);
      setMembers(m);
      setHandoff(h);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings");
    }
  }, [stashId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  if (!user) return null;
  if (!stash) {
    return (
      <div className="mx-auto max-w-2xl px-8 py-12 text-muted">
        {error || "Loading…"}
      </div>
    );
  }

  const loadedStash = stash;
  const myRole = members.find((m) => m.user_id === user.id)?.role;
  const isOwner = myRole === "owner";
  const currentVis = inferVisibility(loadedStash);

  async function changeVisibility(v: Visibility) {
    if (!stash || savingVis) return;
    setSavingVis(true);
    setError("");
    try {
      const isPublic = v !== "private";
      const discoverable = v === "public";
      const updated = await updateWorkspace(stash.id, {
        is_public: isPublic,
        discoverable,
      });
      setStash(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update visibility");
    } finally {
      setSavingVis(false);
    }
  }

  async function toggleAutoCurate() {
    if (!handoff) return;
    if (handoff.pinned_at) {
      const updated = await unpinStashHandoff(stashId);
      setHandoff(updated);
    } else {
      const updated = await editStashHandoff(stashId, handoff.body_markdown ?? "");
      setHandoff(updated);
    }
  }

  async function changeMemberRole(userId: string, role: "owner" | "editor" | "viewer") {
    await setWorkspaceMemberRole(stashId, userId, role);
    await load();
  }

  async function uploadIcon(file: File) {
    const uploaded = await uploadFile(loadedStash.id, file);
    const updated = await updateWorkspace(loadedStash.id, { icon_url: uploaded.url });
    setStash(updated);
  }

  async function clearIcon() {
    const updated = await updateWorkspace(loadedStash.id, { icon_url: null });
    setStash(updated);
  }

  function currentBackground() {
    return backgroundDraft ?? loadedStash.home_background;
  }

  function setBackgroundKind(kind: HomeBackground["kind"]) {
    const current = currentBackground();
    setBackgroundDraft({
      ...current,
      kind,
      image_url: kind === "image" ? current.image_url || "" : null,
    });
  }

  function updateBackground(patch: Partial<HomeBackground>) {
    setBackgroundDraft({ ...currentBackground(), ...patch });
  }

  async function saveBackground() {
    const draft = currentBackground();
    const next: HomeBackground = {
      ...draft,
      image_url: draft.kind === "image" ? (draft.image_url || "").trim() : null,
    };
    if (next.kind === "image" && !next.image_url) {
      setBackgroundError("Image URL is required.");
      return;
    }

    setSavingBackground(true);
    setBackgroundError("");
    try {
      const updated = await updateWorkspace(loadedStash.id, { home_background: next });
      setStash(updated);
      setBackgroundDraft(updated.home_background);
    } catch (e) {
      setBackgroundError(e instanceof Error ? e.message : "Failed to save background");
    } finally {
      setSavingBackground(false);
    }
  }

  async function removeMember(userId: string) {
    if (!confirm("Remove this member from the stash?")) return;
    await kickWorkspaceMember(stashId, userId);
    await load();
  }

  async function handleDelete() {
    if (!confirm(`Delete "${loadedStash.name}"? This cannot be undone.`)) return;
    await deleteWorkspace(loadedStash.id);
    resetStashNavigationCache();
    router.push("/");
  }

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-8 py-10">
        <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
          Settings
        </h1>
        <p className="mt-1 text-[13px] text-muted">{loadedStash.name}</p>

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
                    {m.display_name || m.name}
                  </div>
                  <div className="text-[11.5px] text-muted">@{m.name}</div>
                </div>
                <div className="flex items-center gap-2">
                  {isOwner && m.user_id !== user.id ? (
                    <>
                      <select
                        value={m.role}
                        onChange={(e) =>
                          changeMemberRole(
                            m.user_id,
                            e.target.value as "owner" | "editor" | "viewer"
                          )
                        }
                        className="rounded border border-border bg-surface px-2 py-1 text-[12px]"
                      >
                        <option value="viewer">Viewer</option>
                        <option value="editor">Editor</option>
                        <option value="owner">Owner</option>
                      </select>
                      <button
                        onClick={() => removeMember(m.user_id)}
                        className="text-[11.5px] text-red-500 hover:underline"
                      >
                        Remove
                      </button>
                    </>
                  ) : (
                    <span className="rounded bg-raised px-2 py-0.5 text-[11.5px] text-muted">
                      {m.role}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Visibility">
          {(["private", "unlisted", "public"] as Visibility[]).map((v) => (
            <label
              key={v}
              className={
                "flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2 " +
                (currentVis === v
                  ? "border-[var(--color-brand-500)] bg-[var(--color-brand-50)]"
                  : "border-border bg-base hover:bg-raised")
              }
            >
              <input
                type="radio"
                name="visibility"
                checked={currentVis === v}
                onChange={() => changeVisibility(v)}
                disabled={!isOwner || savingVis}
                className="mt-1"
              />
              <div className="min-w-0">
                <div className="text-[13.5px] font-medium text-foreground capitalize">
                  {v}
                </div>
                <div className="text-[11.5px] text-muted">
                  {v === "private"
                    ? "Only members can see this stash."
                    : v === "unlisted"
                    ? "Anyone with the link can view — not listed in discover."
                    : "Listed in the public discover catalog."}
                </div>
              </div>
            </label>
          ))}
          {!isOwner && (
            <p className="mt-2 text-[11.5px] text-muted">
              Only the owner can change visibility.
            </p>
          )}
        </Section>

        <Section title="Homepage background">
          <div className="rounded-lg border border-border bg-base px-3 py-2">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[13.5px] font-medium text-foreground">Top background</div>
                <div className="text-[11.5px] text-muted">Gradient or image</div>
              </div>
              <div className="flex rounded-md border border-border bg-surface p-0.5">
                {(["gradient", "image"] as const).map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    onClick={() => setBackgroundKind(kind)}
                    disabled={!isOwner}
                    className={
                      "rounded px-2 py-1 text-[12px] capitalize " +
                      (currentBackground().kind === kind
                        ? "bg-base text-foreground shadow-sm"
                        : "text-muted hover:text-foreground")
                    }
                  >
                    {kind}
                  </button>
                ))}
              </div>
            </div>

            {currentBackground().kind === "gradient" ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <ColorField
                  label="Start"
                  value={currentBackground().gradient_start}
                  disabled={!isOwner}
                  onChange={(gradient_start) => updateBackground({ gradient_start })}
                />
                <ColorField
                  label="Middle"
                  value={currentBackground().gradient_middle}
                  disabled={!isOwner}
                  onChange={(gradient_middle) => updateBackground({ gradient_middle })}
                />
                <ColorField
                  label="End"
                  value={currentBackground().gradient_end}
                  disabled={!isOwner}
                  onChange={(gradient_end) => updateBackground({ gradient_end })}
                />
              </div>
            ) : (
              <label className="mt-3 flex flex-col gap-1.5">
                <span className="text-[12px] font-medium text-foreground">Image URL</span>
                <input
                  value={currentBackground().image_url || ""}
                  onChange={(e) => updateBackground({ image_url: e.target.value })}
                  disabled={!isOwner}
                  placeholder="https://example.com/cover.jpg"
                  className="rounded-md border border-border bg-surface px-3 py-2 text-[13px] text-foreground placeholder:text-muted focus:border-[var(--color-brand-500)] focus:outline-none disabled:opacity-60"
                />
              </label>
            )}

            <div
              className="mt-3 h-20 rounded-md border border-border"
              style={homeBackgroundStyle(currentBackground())}
            />

            {backgroundError && (
              <div className="mt-2 text-[12px] text-red-500">{backgroundError}</div>
            )}

            {isOwner ? (
              <div className="mt-3 flex justify-end">
                <button
                  type="button"
                  onClick={saveBackground}
                  disabled={savingBackground}
                  className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-50"
                >
                  {savingBackground ? "Saving…" : "Save background"}
                </button>
              </div>
            ) : (
              <p className="mt-2 text-[11.5px] text-muted">
                Only the owner can update the homepage background.
              </p>
            )}
          </div>
        </Section>

        <Section title="Icon">
          <ImageField
            label="Icon"
            sub="Square logo for the stash hero."
            url={loadedStash.icon_url ?? null}
            canEdit={isOwner}
            onUpload={uploadIcon}
            onClear={clearIcon}
            previewClass="h-12 w-12 rounded-md object-cover"
          />
        </Section>

        <Section title="Handoff document">
          <div className="flex items-center justify-between rounded-lg border border-border bg-base px-3 py-2">
            <div>
              <div className="text-[13.5px] font-medium text-foreground">
                Auto-curate handoff
              </div>
              <div className="text-[11.5px] text-muted">
                When on, a sleep-time agent keeps the handoff document up to date.
              </div>
            </div>
            <button
              onClick={toggleAutoCurate}
              disabled={!handoff}
              className={
                "rounded-md px-3 py-1 text-[12px] font-medium " +
                (handoff?.pinned_at
                  ? "border border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100"
                  : "bg-[var(--color-brand-600)] text-white hover:bg-[var(--color-brand-700)]")
              }
            >
              {handoff?.pinned_at ? "Off — turn on" : "On"}
            </button>
          </div>
        </Section>

        {isOwner && (
          <Section title="Danger zone">
            <button
              onClick={handleDelete}
              className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-[13px] font-medium text-red-700 hover:bg-red-100"
            >
              Delete this stash
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

function ColorField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12px] font-medium text-foreground">{label}</span>
      <div className="flex items-center gap-2 rounded-md border border-border bg-surface px-2 py-1.5">
        <input
          type="color"
          value={colorInputValue(value)}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          disabled={disabled}
          className="h-7 w-7 shrink-0 cursor-pointer rounded border-0 bg-transparent p-0 disabled:cursor-default"
        />
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          pattern="^#[0-9A-Fa-f]{6}$"
          className="min-w-0 flex-1 bg-transparent font-mono text-[12px] text-foreground focus:outline-none disabled:opacity-60"
        />
      </div>
    </label>
  );
}

function colorInputValue(value: string) {
  return /^#[0-9A-Fa-f]{6}$/.test(value) ? value : "#000000";
}

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
