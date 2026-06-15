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
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { useConfirm } from "../../../../../components/ConfirmDialog";
import { useActiveWorkspaceId } from "../../../../../components/ShellChromeContext";
import { useAuth } from "../../../../../hooks/useAuth";
import {
  getPublicSkill,
  unpublishSkill,
  updateSkill,
  uploadFile,
  type PublicSkillDetail,
} from "../../../../../lib/api";
import { resetSkillNavigationCache } from "../../../../../lib/skillNavigationCache";

// Settings for the publish record of a skill. The skill's contents live in
// its folder (edited through the workspace); this page only manages how the
// published version presents and whether it stays shared.
export default function SkillSettingsPageClient({ slug }: { slug: string }) {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const confirm = useConfirm();
  const [data, setData] = useState<PublicSkillDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("");

  const skill = data?.skill ?? null;

  useBreadcrumbs(
    [
      { label: "Skills", href: "/skills" },
      { label: skill?.title ?? "Skill", href: `/skills/${slug}` },
      { label: "Settings" },
    ],
    `skill-settings/${slug}/${skill?.id ?? "loading"}`
  );
  useActiveWorkspaceId(skill?.workspace_id ?? null);

  const load = useCallback(async () => {
    if (!user) return;

    setLoading(true);
    setError("");
    setMessage("");

    try {
      const nextData = await getPublicSkill(slug);
      setData(nextData);
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, [slug, user]);

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace(`/login?next=${encodeURIComponent(`/skills/${slug}/settings`)}`);
    }
  }, [authLoading, router, slug, user]);

  useEffect(() => {
    if (user) void load();
  }, [load, user]);

  useEffect(() => {
    if (!skill) return;
    setTitle(skill.title);
  }, [skill]);

  if (authLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted">
        Loading...
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-muted">
        Loading settings...
      </div>
    );
  }

  if (!data || !skill) {
    return (
      <div className="mx-auto max-w-md px-8 py-20 text-center">
        <h1 className="font-display text-[26px] font-bold text-foreground">
          Skill settings
        </h1>
        <p className="mt-2 text-[13px] text-muted">
          {error || "This skill is unavailable."}
        </p>
        <Link
          href={`/skills/${slug}`}
          className="mt-4 inline-flex rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
        >
          Open Skill
        </Link>
      </div>
    );
  }

  if (!data.can_write) {
    return (
      <div className="mx-auto max-w-md px-8 py-20 text-center">
        <h1 className="font-display text-[26px] font-bold text-foreground">
          Skill settings
        </h1>
        <p className="mt-2 text-[13px] text-muted">
          You do not have edit access to this skill.
        </p>
        <Link
          href={`/skills/${skill.slug}`}
          className="mt-4 inline-flex rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
        >
          Open Skill
        </Link>
      </div>
    );
  }

  async function saveGeneral(e: FormEvent) {
    e.preventDefault();
    if (!skill) return;

    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setError("Title is required.");
      return;
    }

    setSaving("general");
    setError("");
    setMessage("");
    try {
      const updated = await updateSkill(skill.id, {
        title: trimmedTitle,
      });
      setData((current) => (current ? { ...current, skill: updated } : current));
      resetSkillNavigationCache();
      setMessage("Saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save settings");
    } finally {
      setSaving("");
    }
  }

  async function uploadAndSet(file: File, field: "cover_image_url" | "icon_url") {
    if (!skill) return;

    setSaving("branding");
    setError("");
    try {
      const uploaded = await uploadFile(skill.workspace_id, file);
      const updated = await updateSkill(skill.id, { [field]: uploaded.url });
      setData((current) => (current ? { ...current, skill: updated } : current));
      resetSkillNavigationCache();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not upload image");
    } finally {
      setSaving("");
    }
  }

  async function clearImage(field: "cover_image_url" | "icon_url") {
    if (!skill) return;

    setSaving("branding");
    setError("");
    try {
      const updated = await updateSkill(skill.id, { [field]: null });
      setData((current) => (current ? { ...current, skill: updated } : current));
      resetSkillNavigationCache();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not clear image");
    } finally {
      setSaving("");
    }
  }

  async function toggleDiscoverable(nextDiscoverable: boolean) {
    if (!skill) return;

    setSaving("discover");
    setError("");
    try {
      const updated = await updateSkill(skill.id, { discoverable: nextDiscoverable });
      setData((current) => (current ? { ...current, skill: updated } : current));
      resetSkillNavigationCache();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update Discover");
    } finally {
      setSaving("");
    }
  }

  async function handleStopSharing() {
    if (!skill) return;
    const ok = await confirm({
      title: `Stop sharing "${skill.title}"?`,
      body: "The share link stops working; the skill folder and its files stay in your workspace.",
      confirmLabel: "Stop sharing",
    });
    if (!ok) return;

    setSaving("unpublish");
    setError("");
    try {
      await unpublishSkill(skill.id);
      resetSkillNavigationCache();
      router.push(`/workspaces/${skill.workspace_id}/skills`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not stop sharing");
      setSaving("");
    }
  }

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-8 py-10">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
                Settings
              </h1>
              <p className="mt-1 truncate text-[13px] text-muted">{skill.title}</p>
            </div>
            <Link
              href={`/skills/${skill.slug}`}
              className="flex-shrink-0 rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
            >
              Open Skill
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
              <label className="block text-[12px] font-medium text-muted" htmlFor="skill-title">
                Title
              </label>
              <input
                id="skill-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-[13.5px] text-foreground outline-none focus:border-[var(--color-brand-400)]"
              />

              <div className="mt-4 flex items-center gap-3">
                <button
                  type="submit"
                  disabled={saving === "general" || !title.trim()}
                  className="cursor-pointer rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-50"
                >
                  {saving === "general" ? "Saving..." : "Save changes"}
                </button>
              </div>
            </form>
          </Section>

          <Section title="Sharing">
            <div className="rounded-lg border border-border bg-base px-3 py-3 text-[13px] text-foreground">
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted">URL</span>
                <span className="truncate font-mono text-[12px]">/skills/{skill.slug}</span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <span className="text-muted">Views</span>
                <span>{skill.view_count}</span>
              </div>
              <label className="mt-3 flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface px-2 py-1.5">
                <input
                  type="checkbox"
                  checked={skill.discoverable}
                  disabled={saving === "discover"}
                  onChange={(e) => void toggleDiscoverable(e.target.checked)}
                />
                <span className="text-[12px] text-foreground">List on Discover</span>
              </label>
            </div>
          </Section>

          <Section title="Branding">
            <ImageField
              label="Banner"
              sub="Wide image rendered above the Skill header."
              url={skill.cover_image_url}
              onUpload={(file) => uploadAndSet(file, "cover_image_url")}
              onClear={() => clearImage("cover_image_url")}
              previewClass="h-16 w-full rounded-md object-cover"
            />
            <ImageField
              label="Icon"
              sub="Square logo for this skill."
              url={skill.icon_url}
              onUpload={(file) => uploadAndSet(file, "icon_url")}
              onClear={() => clearImage("icon_url")}
              previewClass="h-12 w-12 rounded-md object-cover"
            />
          </Section>

          <Section title="Danger zone">
            <button
              type="button"
              onClick={handleStopSharing}
              disabled={saving === "unpublish"}
              className="cursor-pointer rounded-md border border-red-300 bg-red-50 px-3 py-2 text-[13px] font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
            >
              {saving === "unpublish" ? "Stopping..." : "Stop sharing"}
            </button>
          </Section>
        </div>
      </div>
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
  const inputId = `skill-${label.toLowerCase()}-upload`;

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
              className="cursor-pointer text-[11.5px] text-muted hover:text-foreground"
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
