"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useState,
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
} from "react";
import AppShell from "../../../../components/AppShell";
import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import CustomSelect from "../../../../components/CustomSelect";
import { StashIcon } from "../../../../components/StashIcons";
import { useAuth } from "../../../../hooks/useAuth";
import {
  addStashMember,
  ApiError,
  deleteStash,
  getPublicStash,
  listStashMembers,
  removeStashMember,
  searchUsers,
  updateStash,
  uploadFile,
  type PublicStashDetail,
  type StashMember,
  type StashMemberPermission,
} from "../../../../lib/api";
import { resetStashNavigationCache } from "../../../../lib/stashNavigationCache";
import type { UserSearchResult } from "../../../../lib/types";

type StashAccess = PublicStashDetail["stash"]["access"];

const ACCESS_OPTIONS = [
  { value: "workspace", label: "Workspace" },
  { value: "private", label: "Private" },
  { value: "public", label: "Public" },
];

const PERMISSION_OPTIONS = [
  { value: "read", label: "Read" },
  { value: "write", label: "Write" },
  { value: "admin", label: "Admin" },
];

export default function StashSettingsPageClient({ slug }: { slug: string }) {
  const router = useRouter();
  const { user, loading: authLoading, logout } = useAuth();
  const [data, setData] = useState<PublicStashDetail | null>(null);
  const [members, setMembers] = useState<StashMember[]>([]);
  const [canManageMembers, setCanManageMembers] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("");
  const [access, setAccess] = useState<StashAccess>("workspace");
  const [discoverable, setDiscoverable] = useState(false);
  const [userQuery, setUserQuery] = useState("");
  const [userResults, setUserResults] = useState<UserSearchResult[]>([]);
  const [newMemberPermission, setNewMemberPermission] =
    useState<StashMemberPermission>("read");
  const [memberMessage, setMemberMessage] = useState("");

  const stash = data?.stash ?? null;

  useBreadcrumbs(
    [
      { label: "Stashes", href: "/stashes" },
      { label: stash?.title ?? "Stash", href: `/stashes/${slug}` },
      { label: "Settings" },
    ],
    `stash-settings/${slug}/${stash?.id ?? "loading"}`
  );

  const load = useCallback(async () => {
    if (!user) return;

    setLoading(true);
    setError("");
    setMessage("");

    try {
      const nextData = await getPublicStash(slug);
      setData(nextData);

      if (!nextData.can_write) {
        setMembers([]);
        setCanManageMembers(false);
        return;
      }

      try {
        setMembers(await listStashMembers(nextData.stash.id));
        setCanManageMembers(true);
      } catch (e) {
        if (e instanceof ApiError && e.status === 403) {
          setMembers([]);
          setCanManageMembers(false);
          return;
        }
        throw e;
      }
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, [slug, user]);

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace(`/login?next=${encodeURIComponent(`/stashes/${slug}/settings`)}`);
    }
  }, [authLoading, router, slug, user]);

  useEffect(() => {
    if (user) void load();
  }, [load, user]);

  useEffect(() => {
    if (!stash) return;
    setTitle(stash.title);
    setAccess(stash.access);
    setDiscoverable(stash.discoverable);
  }, [stash]);

  if (authLoading || !user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background text-muted">
        Loading...
      </main>
    );
  }

  if (loading) {
    return (
      <AppShell user={user} onLogout={logout} activeWorkspaceId={stash?.workspace_id ?? null}>
        <div className="flex min-h-[50vh] items-center justify-center text-muted">
          Loading settings...
        </div>
      </AppShell>
    );
  }

  if (!data || !stash) {
    return (
      <AppShell user={user} onLogout={logout}>
        <div className="mx-auto max-w-md px-8 py-20 text-center">
          <h1 className="font-display text-[26px] font-bold text-foreground">
            Stash settings
          </h1>
          <p className="mt-2 text-[13px] text-muted">
            {error || "This Stash is unavailable."}
          </p>
          <Link
            href={`/stashes/${slug}`}
            className="mt-4 inline-flex rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
          >
            Open Stash
          </Link>
        </div>
      </AppShell>
    );
  }

  if (!data.can_write) {
    return (
      <AppShell user={user} onLogout={logout} activeWorkspaceId={stash.workspace_id}>
        <div className="mx-auto max-w-md px-8 py-20 text-center">
          <h1 className="font-display text-[26px] font-bold text-foreground">
            Stash settings
          </h1>
          <p className="mt-2 text-[13px] text-muted">
            You do not have edit access to this Stash.
          </p>
          <Link
            href={`/stashes/${stash.slug}`}
            className="mt-4 inline-flex rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
          >
            Open Stash
          </Link>
        </div>
      </AppShell>
    );
  }

  async function saveGeneral(e: FormEvent) {
    e.preventDefault();
    if (!stash) return;

    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setError("Title is required.");
      return;
    }

    setSaving("general");
    setError("");
    setMessage("");
    try {
      const nextDiscoverable = access === "public" ? discoverable : false;
      const updated = await updateStash(stash.id, {
        title: trimmedTitle,
        access,
        discoverable: nextDiscoverable,
      });
      setData((current) => (current ? { ...current, stash: updated } : current));
      setDiscoverable(updated.discoverable);
      resetStashNavigationCache();
      setMessage("Saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save settings");
    } finally {
      setSaving("");
    }
  }

  async function uploadAndSet(file: File, field: "cover_image_url" | "icon_url") {
    if (!stash) return;

    setSaving("branding");
    setError("");
    try {
      const uploaded = await uploadFile(stash.workspace_id, file);
      const updated = await updateStash(stash.id, { [field]: uploaded.url });
      setData((current) => (current ? { ...current, stash: updated } : current));
      resetStashNavigationCache();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not upload image");
    } finally {
      setSaving("");
    }
  }

  async function clearImage(field: "cover_image_url" | "icon_url") {
    if (!stash) return;

    setSaving("branding");
    setError("");
    try {
      const updated = await updateStash(stash.id, { [field]: null });
      setData((current) => (current ? { ...current, stash: updated } : current));
      resetStashNavigationCache();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not clear image");
    } finally {
      setSaving("");
    }
  }

  async function searchForUsers(e: FormEvent) {
    e.preventDefault();
    if (!userQuery.trim()) return;

    setSaving("members");
    setMemberMessage("");
    try {
      setUserResults(await searchUsers(userQuery.trim()));
    } catch (e) {
      setMemberMessage(e instanceof Error ? e.message : "Could not search users");
    } finally {
      setSaving("");
    }
  }

  async function refreshMembers() {
    if (!stash) return;
    setMembers(await listStashMembers(stash.id));
  }

  async function addMember(userId: string) {
    if (!stash) return;

    setSaving("members");
    setMemberMessage("");
    try {
      await addStashMember(stash.id, userId, newMemberPermission);
      await refreshMembers();
      setUserQuery("");
      setUserResults([]);
      setMemberMessage("Added.");
      resetStashNavigationCache();
    } catch (e) {
      setMemberMessage(e instanceof Error ? e.message : "Could not add member");
    } finally {
      setSaving("");
    }
  }

  async function changeMemberPermission(
    userId: string,
    permission: StashMemberPermission
  ) {
    if (!stash) return;

    setSaving("members");
    setMemberMessage("");
    try {
      await addStashMember(stash.id, userId, permission);
      await refreshMembers();
      setMemberMessage("Updated.");
      resetStashNavigationCache();
    } catch (e) {
      setMemberMessage(e instanceof Error ? e.message : "Could not update member");
    } finally {
      setSaving("");
    }
  }

  async function removeMember(userId: string) {
    if (!stash) return;
    if (!confirm("Remove this member from the Stash?")) return;

    setSaving("members");
    setMemberMessage("");
    try {
      await removeStashMember(stash.id, userId);
      await refreshMembers();
      resetStashNavigationCache();
    } catch (e) {
      setMemberMessage(e instanceof Error ? e.message : "Could not remove member");
    } finally {
      setSaving("");
    }
  }

  async function handleDelete() {
    if (!stash) return;
    if (!confirm(`Delete "${stash.title}"? This cannot be undone.`)) return;

    setSaving("delete");
    setError("");
    try {
      await deleteStash(stash.id);
      resetStashNavigationCache();
      router.push(`/workspaces/${stash.workspace_id}/stashes`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete Stash");
      setSaving("");
    }
  }

  const ownerLabel = stash.owner_display_name || stash.owner_name;

  return (
    <AppShell user={user} onLogout={logout} activeWorkspaceId={stash.workspace_id}>
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-8 py-10">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
                Settings
              </h1>
              <p className="mt-1 truncate text-[13px] text-muted">{stash.title}</p>
            </div>
            <Link
              href={`/stashes/${stash.slug}`}
              className="flex-shrink-0 rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
            >
              Open Stash
            </Link>
          </div>

          {error && (
            <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}
          {message && (
            <div className="mt-4 rounded-lg border border-emerald-300/40 bg-emerald-500/10 px-4 py-2 text-[13px] text-emerald-700">
              {message}
            </div>
          )}

          <Section title="General">
            <form
              onSubmit={saveGeneral}
              className="rounded-lg border border-border bg-base px-3 py-3"
            >
              <label className="block text-[12px] font-medium text-muted" htmlFor="stash-title">
                Title
              </label>
              <input
                id="stash-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-[13.5px] text-foreground outline-none focus:border-[var(--color-brand-400)]"
              />

              <div className="mt-4 grid gap-3 sm:grid-cols-[160px_minmax(0,1fr)]">
                <div>
                  <label className="block text-[12px] font-medium text-muted">
                    Visibility
                  </label>
                  <CustomSelect
                    value={access}
                    options={ACCESS_OPTIONS}
                    onChange={(next) => setAccess(next as StashAccess)}
                    ariaLabel="Stash visibility"
                    className="mt-1 w-full rounded-md border border-border bg-surface px-2.5 py-2 text-[12.5px]"
                  />
                </div>
                <label
                  className={
                    "mt-5 flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-[12.5px] " +
                    (access === "public"
                      ? "cursor-pointer text-foreground"
                      : "cursor-not-allowed text-muted")
                  }
                >
                  <input
                    type="checkbox"
                    checked={access === "public" && discoverable}
                    disabled={access !== "public"}
                    onChange={(e) => setDiscoverable(e.target.checked)}
                  />
                  <span>List on Discover</span>
                </label>
              </div>

              <div className="mt-4 flex items-center gap-3">
                <button
                  type="submit"
                  disabled={saving === "general" || !title.trim()}
                  className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-50"
                >
                  {saving === "general" ? "Saving..." : "Save changes"}
                </button>
              </div>
            </form>
          </Section>

          <Section title="Branding">
            <ImageField
              label="Banner"
              sub="Wide image rendered above the Stash header."
              url={stash.cover_image_url}
              onUpload={(file) => uploadAndSet(file, "cover_image_url")}
              onClear={() => clearImage("cover_image_url")}
              previewClass="h-16 w-full rounded-md object-cover"
            />
            <ImageField
              label="Icon"
              sub="Square logo for this Stash."
              url={stash.icon_url}
              onUpload={(file) => uploadAndSet(file, "icon_url")}
              onClear={() => clearImage("icon_url")}
              previewClass="h-12 w-12 rounded-md object-cover"
            />
          </Section>

          <Section title="Members">
            <div className="rounded-lg border border-border bg-base px-3 py-2">
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[var(--color-brand-100)] text-[var(--color-brand-700)]">
                    <StashIcon />
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-[13.5px] font-medium text-foreground">
                      {ownerLabel}
                    </div>
                    <div className="truncate text-[11.5px] text-muted">
                      @{stash.owner_name}
                    </div>
                  </div>
                </div>
                <span className="rounded bg-raised px-2 py-0.5 text-[11.5px] text-muted">
                  admin
                </span>
              </div>
            </div>

            {canManageMembers ? (
              <>
                <ul className="flex flex-col gap-2">
                  {members.map((member) => (
                    <li
                      key={member.user_id}
                      className="flex items-center justify-between gap-3 rounded-lg border border-border bg-base px-3 py-2"
                    >
                      <div className="min-w-0">
                        <div className="truncate text-[13.5px] font-medium text-foreground">
                          {member.display_name || member.name}
                        </div>
                        <div className="truncate text-[11.5px] text-muted">
                          @{member.name}
                        </div>
                      </div>
                      <div className="flex flex-shrink-0 items-center gap-2">
                        <CustomSelect
                          value={member.permission}
                          options={PERMISSION_OPTIONS}
                          onChange={(next) =>
                            changeMemberPermission(
                              member.user_id,
                              next as StashMemberPermission
                            )
                          }
                          ariaLabel={`Permission for ${member.name}`}
                          className="min-w-[82px] rounded border border-border bg-surface px-2 py-1 text-[12px]"
                          align="right"
                        />
                        {member.user_id !== user.id && (
                          <button
                            type="button"
                            onClick={() => removeMember(member.user_id)}
                            className="text-[11.5px] text-red-500 hover:underline"
                          >
                            Remove
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>

                <form
                  onSubmit={searchForUsers}
                  className="rounded-lg border border-border bg-base px-3 py-3"
                >
                  <label className="block text-[12px] font-medium text-muted" htmlFor="member-search">
                    Add member
                  </label>
                  <div className="mt-1 flex gap-2">
                    <input
                      id="member-search"
                      value={userQuery}
                      onChange={(e) => setUserQuery(e.target.value)}
                      placeholder="Search users"
                      className="min-w-0 flex-1 rounded-md border border-border bg-surface px-3 py-2 text-[13px] text-foreground outline-none focus:border-[var(--color-brand-400)]"
                    />
                    <CustomSelect
                      value={newMemberPermission}
                      options={PERMISSION_OPTIONS}
                      onChange={(next) =>
                        setNewMemberPermission(next as StashMemberPermission)
                      }
                      ariaLabel="New member permission"
                      className="min-w-[86px] rounded-md border border-border bg-surface px-2 py-2 text-[12px]"
                      align="right"
                    />
                    <button
                      type="submit"
                      disabled={saving === "members" || !userQuery.trim()}
                      className="rounded-md border border-border bg-base px-3 py-2 text-[12.5px] font-medium text-foreground hover:bg-raised disabled:opacity-50"
                    >
                      Search
                    </button>
                  </div>
                  {userResults.length > 0 && (
                    <div className="mt-3 flex flex-col gap-1">
                      {userResults.map((result) => (
                        <button
                          key={result.id}
                          type="button"
                          onClick={() => addMember(result.id)}
                          className="flex items-center justify-between rounded-md px-2 py-1.5 text-left hover:bg-raised"
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-[13px] font-medium text-foreground">
                              {result.display_name || result.name}
                            </span>
                            <span className="block truncate text-[11.5px] text-muted">
                              @{result.name}
                            </span>
                          </span>
                          <span className="text-[11.5px] text-muted">Add</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {memberMessage && (
                    <div className="mt-2 text-[12px] text-muted">{memberMessage}</div>
                  )}
                </form>
              </>
            ) : (
              <div className="rounded-lg border border-border bg-base px-3 py-2 text-[13px] text-muted">
                Only Stash admins can manage members.
              </div>
            )}
          </Section>

          <Section title="Danger zone">
            <button
              type="button"
              onClick={handleDelete}
              disabled={saving === "delete"}
              className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-[13px] font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
            >
              {saving === "delete" ? "Deleting..." : "Delete this Stash"}
            </button>
          </Section>
        </div>
      </div>
    </AppShell>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-[12px] font-semibold uppercase tracking-wider text-muted">
        {title}
      </h2>
      <div className="mt-3 flex flex-col gap-2">{children}</div>
    </section>
  );
}

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
  onUpload: (file: File) => Promise<void>;
  onClear: () => Promise<void>;
  previewClass: string;
}) {
  const inputId = `stash-${label.toLowerCase()}-upload`;

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void onUpload(file);
  }

  return (
    <div className="rounded-lg border border-border bg-base px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[13.5px] font-medium text-foreground">{label}</div>
          <div className="text-[11.5px] text-muted">{sub}</div>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
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
            onChange={handleChange}
          />
          {url && (
            <button
              type="button"
              onClick={() => void onClear()}
              className="text-[11.5px] text-muted hover:text-foreground"
            >
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
