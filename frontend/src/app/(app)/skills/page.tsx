"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useConfirm } from "@/components/ConfirmDialog";
import CopyableCommandBlock from "@/components/CopyableCommandBlock";
import {
  CardGridSkeleton,
  SkillsGridSkeleton,
} from "@/components/SkeletonStates";
import { PinIcon, SkillIcon } from "@/components/SkillIcons";
import SkillCard, {
  PUBLISH_COLOR,
  PublishBadge,
} from "@/components/skill/SkillCard";
import ForkSkillCardButton from "@/components/skill/ForkSkillCardButton";
import { SelectBox } from "@/components/content/file-browser/ItemsList";
import {
  forkSkill,
  ApiError,
  API_BASE,
  createFolder,
  createPage,
  deleteFolder,
  listSkills,
  listSkillsSharedWithMe,
  type SharedSkill,
  type Skill,
  type PublicSkillCard,
} from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { SKILL_MD, skillMdTemplate } from "@/lib/localSkill";
import { usePins } from "@/lib/pins";
import { skillSlugFromInput } from "@/lib/skillLinks";
import { refreshSidebar } from "@/lib/skillNavigationCache";

type ViewKey = "grid" | "list";
// The primary axis: which set of Skills you're looking at. Yours and Shared
// share the view toggle / quick-access; Discover is its own public-library
// surface. Each row carries its own Private/Shared/Public badge — there's no
// visibility filter to learn.
type Tab = "yours" | "shared" | "discover";

const VIEW_STORAGE_KEY = "stash_skills_view";

const COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"];

const TAB_COPY: Record<Tab, string> = {
  yours:
    "Your Skill folders. Share them with people or publish them to the public library.",
  shared: "Skill folders other people shared with you, plus adding a skill by link.",
  discover: "Public skills from the community — fork one into your Skills.",
};

export default function SkillsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const pins = usePins("skills");
  const confirm = useConfirm();

  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [sharedSkills, setSharedSkills] = useState<SharedSkill[]>([]);
  const [tab, setTab] = useState<Tab>("yours");
  const [view, setView] = useState<ViewKey>("grid");
  const [error, setError] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  function toggleSelect(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(VIEW_STORAGE_KEY) as ViewKey | null;
    if (saved === "grid" || saved === "list") setView(saved);
  }, []);

  function setViewPersisted(next: ViewKey) {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_STORAGE_KEY, next);
    } catch {
      /* localStorage unavailable */
    }
  }

  const load = useCallback(async () => {
    try {
      setSkills(await listSkills());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load Skills");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Skill folders others shared directly with you (folder shares) — surfaced
  // in the "Shared with you" section. Non-critical: failure leaves it empty.
  useEffect(() => {
    listSkillsSharedWithMe()
      .then(setSharedSkills)
      .catch(() => setSharedSkills([]));
  }, []);

  async function newSkill() {
    const name = window.prompt("Skill name?");
    if (!name?.trim()) return;
    try {
      const folder = await createFolder(name.trim());
      await createPage(SKILL_MD, folder.id, skillMdTemplate(name.trim()));
      if (user) await refreshSidebar().catch(() => {});
      router.push(`/skills/folder/${folder.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create skill");
    }
  }

  const visible = useMemo(() => {
    if (!skills) return [];
    return [...skills].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );
  }, [skills]);

  const pinnedSkills = useMemo(
    () => (skills ?? []).filter((s) => pins.pinnedSet.has(s.folder_id)),
    [skills, pins.pinnedSet]
  );
  const recentSkills = useMemo(
    () =>
      (skills ?? [])
        .filter((s) => !pins.pinnedSet.has(s.folder_id))
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
        .slice(0, 6),
    [skills, pins.pinnedSet]
  );

  const selectedSkills = (skills ?? []).filter((s) => selectedIds.has(s.folder_id));

  async function bulkDeleteSkills() {
    if (selectedSkills.length === 0) return;
    const ok = await confirm({
      title: `Delete ${selectedSkills.length} skill${selectedSkills.length === 1 ? "" : "s"}?`,
      body: "Their files will be deleted too. This can't be undone.",
      confirmLabel: "Delete",
    });
    if (!ok) return;
    try {
      for (const skill of selectedSkills) {
        await deleteFolder(skill.folder_id);
      }
      clearSelection();
      await load();
      if (user) refreshSidebar().catch(() => {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (skills === null) {
    return <SkillsGridSkeleton />;
  }

  const isPinned = (s: Skill) => pins.pinnedSet.has(s.folder_id);

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1120px] px-12 pb-20 pt-8">
        <div className="flex items-center justify-between gap-4">
          <h1 className="m-0 font-display text-[21px] font-bold tracking-tight text-foreground">
            Skills
          </h1>
          <button
            type="button"
            onClick={() => void newSkill()}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-md bg-[var(--color-brand-600)] px-2.5 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
          >
            <PlusGlyph /> New Skill
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        {/* The primary selector: Yours / Shared with you / Discover. */}
        <SkillTabs
          tab={tab}
          onChange={setTab}
          yoursCount={skills.length}
          sharedCount={sharedSkills.length}
        />
        <p className="mt-2 text-[12.5px] text-muted-foreground">{TAB_COPY[tab]}</p>

        {/* Quick-access + the view toolbar belong to your held Skills, so
            they sit under Yours, not Discover. */}
        {tab === "yours" && (pinnedSkills.length > 0 || recentSkills.length > 0) && (
          <SkillQuickAccess
            pinned={pinnedSkills}
            recent={recentSkills}
            isPinned={isPinned}
            onTogglePin={(s) => pins.toggle(s.folder_id)}
          />
        )}

        {tab === "yours" && (
          <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
            <SkillViewToggle view={view} onChange={setViewPersisted} />
          </div>
        )}

        {tab === "yours" && (
          <div className="mt-4">
            {visible.length > 0 ? (
              <SkillCollection
                skills={visible}
                view={view}
                isPinned={isPinned}
                onTogglePin={(s) => pins.toggle(s.folder_id)}
                selectedIds={selectedIds}
                onToggleSelect={toggleSelect}
              />
            ) : (
              <NoSkillsYet onBrowseDiscover={() => setTab("discover")} />
            )}
          </div>
        )}

        {tab === "shared" && (
          <div className="mt-4">
            {sharedSkills.length > 0 ? (
              <div className="overflow-hidden rounded-xl border border-border bg-surface">
                {sharedSkills.map((shared) => (
                  <SharedSkillRow key={shared.folder_id} shared={shared} />
                ))}
              </div>
            ) : (
              <EmptyHint>Nothing shared with you yet.</EmptyHint>
            )}
            <ExternalSkillLinkForm onAdded={() => void load()} />
          </div>
        )}

        {tab === "discover" && <DiscoverSection />}
      </div>

      {selectedSkills.length > 0 && (
        <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center">
          <div className="pointer-events-auto flex items-center gap-3 rounded-lg border border-border bg-foreground px-4 py-2 text-[13px] text-background shadow-lg">
            <span className="font-medium">{selectedSkills.length} selected</span>
            <button
              type="button"
              onClick={() => void bulkDeleteSkills()}
              className="cursor-pointer rounded-md border border-background/40 px-2 py-0.5 text-[12px] font-semibold hover:bg-background/10"
            >
              Delete
            </button>
            <button
              type="button"
              onClick={clearSelection}
              className="ml-1 cursor-pointer text-[18px] leading-none text-background/70 hover:text-background"
              aria-label="Clear selection"
            >
              ×
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ExternalSkillLinkForm({ onAdded }: { onAdded: () => void }) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const slug = skillSlugFromInput(input);
    if (!slug) {
      setError("Paste a Skill URL like /skills/product-plan or a Skill slug.");
      setMessage("");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    try {
      const forked = await forkSkill(slug);
      setInput("");
      setMessage(`Added ${forked.name} to your Skills.`);
      onAdded();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add skill");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mt-4 rounded-lg border border-border-subtle bg-surface px-3 py-3"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <label className="text-[12px] font-medium text-foreground" htmlFor="external-skill-link">
            Add external skill by link
          </label>
          <input
            id="external-skill-link"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="https://.../skills/product-plan"
            className="mt-1 w-full rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:border-brand focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="cursor-pointer rounded-md bg-[var(--color-brand-600)] px-3 py-2 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-45 sm:mt-6"
        >
          {busy ? "Adding…" : "Add Skill"}
        </button>
      </div>
      {error ? <p className="mt-2 text-[12px] text-red-500">{error}</p> : null}
      {message ? <p className="mt-2 text-[12px] text-muted-foreground">{message}</p> : null}
    </form>
  );
}

function PlusGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

// The primary selector as an underline tab bar. Yours/Shared carry a live count;
// Discover is the public library (no owned count).
function SkillTabs({
  tab,
  onChange,
  yoursCount,
  sharedCount,
}: {
  tab: Tab;
  onChange: (next: Tab) => void;
  yoursCount: number;
  sharedCount: number;
}) {
  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "yours", label: "Yours", count: yoursCount },
    { key: "shared", label: "Shared with you", count: sharedCount },
    { key: "discover", label: "Discover" },
  ];
  return (
    <div className="mt-5 flex gap-1 border-b border-border">
      {tabs.map((t) => {
        const active = tab === t.key;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={
              "-mb-px cursor-pointer border-b-2 px-3 py-2 text-[13px] transition-colors " +
              (active
                ? "border-[var(--color-brand-600)] font-semibold text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
            {t.count !== undefined && (
              <span className="ml-1.5 text-[11px] text-muted-foreground">{t.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[12.5px] text-muted-foreground">
      {children}
    </p>
  );
}

// Empty state for the Yours tab: point at the CLI create command and the
// public library instead of dead-ending.
function NoSkillsYet({ onBrowseDiscover }: { onBrowseDiscover: () => void }) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[12.5px] text-muted-foreground">
      <p className="m-0">No skills yet.</p>
      <p className="m-0 mt-1.5">Create one from your terminal:</p>
      <div className="mt-3">
        <CopyableCommandBlock commands={'stash skills create "<name>"'} />
      </div>
      <p className="m-0 mt-3">
        Or{" "}
        <button
          type="button"
          onClick={onBrowseDiscover}
          className="cursor-pointer text-[var(--color-brand-600)] underline underline-offset-2 hover:text-[var(--color-brand-700)]"
        >
          browse Discover
        </button>{" "}
        and fork a public skill into your Skills.
      </p>
    </div>
  );
}

// A skill folder shared with you, as a drive-style row. View opens the public
// skill page when it's published, else the shared folder route.
function sharedSkillHref(shared: SharedSkill): string {
  if (shared.slug) return `/skills/${shared.slug}`;
  return `/folders/${shared.folder_id}`;
}

function SharedSkillRow({ shared }: { shared: SharedSkill }) {
  return (
    <div
      className="grid items-center gap-3 border-b border-border-subtle px-4 py-2 text-[13px] last:border-b-0"
      style={{ gridTemplateColumns: "minmax(0,2fr) minmax(0,1fr) auto" }}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center text-[var(--color-brand-600)]">
          <SkillIcon />
        </span>
        <span className="min-w-0 truncate font-medium text-foreground">{shared.name}</span>
        {shared.description && (
          <span className="min-w-0 truncate text-[12px] text-muted-foreground">
            {shared.description}
          </span>
        )}
      </div>
      <span className="truncate text-[12px] text-muted-foreground">
        shared by {shared.shared_by ?? "someone"}
      </span>
      <div className="flex items-center justify-end">
        <Link
          href={sharedSkillHref(shared)}
          className="rounded-md bg-[var(--color-brand-600)] px-2 py-1 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
        >
          View
        </Link>
      </div>
    </div>
  );
}

// --- Discover (public library), inline ---

const DISCOVER_SORTS = ["trending", "newest", "popular"] as const;
type DiscoverSort = (typeof DISCOVER_SORTS)[number];

function discoverSortLabel(sort: DiscoverSort): string {
  if (sort === "popular") return "Most viewed";
  if (sort === "trending") return "Trending";
  return "Newest";
}

async function fetchPublicSkills(params: {
  q?: string;
  sort: DiscoverSort;
}): Promise<PublicSkillCard[]> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) qs.set(key, value);
  }
  const res = await fetch(`${API_BASE}/api/v1/discover/skills${qs.size ? `?${qs}` : ""}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.skills ?? [];
}

// The public marketplace as a section of the Skills page. Self-contained:
// owns its own search/sort/fetch and isn't touched by the page's view
// toggle, pins, or selection (those are for Skills you hold).
function DiscoverSection() {
  const [sort, setSort] = useState<DiscoverSort>("trending");
  const [query, setQuery] = useState("");
  const [skills, setSkills] = useState<PublicSkillCard[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setFetching(true);
    const handle = setTimeout(() => {
      fetchPublicSkills({ q: query || undefined, sort })
        .then((list) => {
          if (!cancelled) setSkills(list);
        })
        .finally(() => {
          if (!cancelled) setFetching(false);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [query, sort]);

  return (
    <section className="mt-4">
      <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
        <div className="mr-auto flex items-baseline gap-2">
          <span className="sys-label" style={{ fontSize: 10.5 }}>
            public library
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex w-[220px] items-center gap-2 rounded-lg border border-border bg-base px-2.5 py-1.5">
            <SearchGlyph />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search public Skills…"
              className="min-w-0 flex-1 border-0 bg-transparent text-[12.5px] text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
          </div>
          <div className="inline-flex gap-0.5 rounded-lg border border-border bg-base p-[3px]">
            {DISCOVER_SORTS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setSort(option)}
                className={
                  "cursor-pointer rounded-md px-2.5 py-[3px] text-[12px] " +
                  (sort === option
                    ? "bg-raised font-semibold text-foreground"
                    : "text-muted-foreground hover:text-foreground")
                }
              >
                {discoverSortLabel(option)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {fetching ? (
        <CardGridSkeleton />
      ) : skills.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12px] text-muted-foreground">
          No public Skills match.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {skills.map((skill, i) => {
            const trending = sort === "trending" && i < 2;
            return (
              <SkillCard
                key={skill.id}
                href={`/skills/${skill.slug}`}
                skill={{
                  title: skill.title,
                  description: skill.description,
                  cover_image_url: skill.cover_image_url,
                  file_count: skill.item_count,
                  updated_at: skill.updated_at,
                }}
                cover={COVERS[i % COVERS.length]}
                badge={
                  trending ? (
                    <span className="absolute left-3 top-2.5 inline-flex items-center gap-1 rounded-full bg-black/80 px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.04em] text-white">
                      ↗ trending
                    </span>
                  ) : undefined
                }
                cornerAction={<ForkSkillCardButton slug={skill.slug} />}
                footer={
                  <>
                    <span className="min-w-0 truncate">
                      {skill.owner_display_name}
                    </span>
                    <span className="inline-flex flex-shrink-0 items-center gap-1 rounded-md border border-border bg-base px-2 py-0.5 text-[11.5px] font-medium text-foreground group-hover:border-[var(--color-brand-300)] group-hover:bg-[var(--color-brand-50)] group-hover:text-[var(--color-brand-700)]">
                      Open →
                    </span>
                  </>
                }
              />
            );
          })}
        </div>
      )}
    </section>
  );
}

function SearchGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted-foreground">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}


function skillHref(skill: Skill): string {
  return `/skills/folder/${skill.folder_id}`;
}

// Publish badge state: null = Private, otherwise Published (+ Discover dot).
function skillPublishBadge(skill: Skill): { discoverable: boolean } | null {
  if (!skill.published) return null;
  return { discoverable: skill.published.discoverable };
}

function SkillCollection({
  skills,
  view,
  isPinned,
  onTogglePin,
  selectedIds,
  onToggleSelect,
}: {
  skills: Skill[];
  view: ViewKey;
  isPinned: (skill: Skill) => boolean;
  onTogglePin: (skill: Skill) => void;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
}) {
  if (view === "list") {
    return (
      <div className="overflow-hidden rounded-xl border border-border bg-surface">
        {skills.map((skill) => (
          <SkillListRow
            key={skill.folder_id}
            skill={skill}
            pinned={isPinned(skill)}
            onTogglePin={onTogglePin}
            selected={selectedIds.has(skill.folder_id)}
            onToggleSelect={onToggleSelect}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {skills.map((skill, i) => {
        return (
          <SkillCard
            key={skill.folder_id}
            href={skillHref(skill)}
            skill={{
              title: skill.name,
              description: skill.description,
              cover_image_url: skill.published?.cover_image_url ?? null,
              icon_url: skill.published?.icon_url ?? null,
              published: skillPublishBadge(skill),
              updated_at: skill.updated_at,
              file_count: skill.file_count,
            }}
            cover={COVERS[i % COVERS.length]}
            selected={selectedIds.has(skill.folder_id)}
            badge={
              <span className="absolute left-2.5 top-2.5 z-10">
                <SelectBox
                  selected={selectedIds.has(skill.folder_id)}
                  onToggle={() => onToggleSelect(skill.folder_id)}
                />
              </span>
            }
            cornerAction={
              <SkillPinButton
                pinned={isPinned(skill)}
                onToggle={() => onTogglePin(skill)}
                onCover
              />
            }
          />
        );
      })}
    </div>
  );
}

function SkillListRow({
  skill,
  pinned,
  onTogglePin,
  selected,
  onToggleSelect,
}: {
  skill: Skill;
  pinned: boolean;
  onTogglePin: (skill: Skill) => void;
  selected: boolean;
  onToggleSelect: (id: string) => void;
}) {
  return (
    <Link
      href={skillHref(skill)}
      className={
        "group grid items-center gap-3 border-b border-border-subtle px-4 py-2 text-[13px] last:border-b-0 " +
        (selected ? "bg-[var(--color-brand-50)]" : "hover:bg-[var(--color-brand-50)]/50")
      }
      style={{ gridTemplateColumns: "auto minmax(0,2fr) minmax(0,1fr) auto auto" }}
    >
      <SelectBox selected={selected} onToggle={() => onToggleSelect(skill.folder_id)} />
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center text-[var(--color-brand-600)]">
          <SkillIcon />
        </span>
        <span className="min-w-0 truncate font-medium text-foreground">{skill.name}</span>
      </div>
      <span className="truncate text-[12px] text-muted-foreground">
        {skill.description && `${skill.description} · `}
        {skill.file_count} file{skill.file_count === 1 ? "" : "s"}
        {skill.updated_at && ` · ${relativeTime(skill.updated_at)}`}
      </span>
      <PublishBadge published={skillPublishBadge(skill)} />
      <span
        className={
          pinned
            ? ""
            : "opacity-0 transition focus-within:opacity-100 group-hover:opacity-100"
        }
      >
        <SkillPinButton pinned={pinned} onToggle={() => onTogglePin(skill)} />
      </span>
    </Link>
  );
}

// Pin toggle reused on skill cards (over the cover), list rows, and the
// quick-access strip. Stops the click from following the card/row link.
function SkillPinButton({
  pinned,
  onToggle,
  onCover,
}: {
  pinned: boolean;
  onToggle: () => void;
  onCover?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={pinned ? "Unpin Skill" : "Pin Skill"}
      aria-pressed={pinned}
      title={pinned ? "Unpin" : "Pin"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
      className={
        "flex h-6 w-6 cursor-pointer items-center justify-center rounded transition " +
        (onCover
          ? "bg-white/70 backdrop-blur hover:bg-white "
          : "hover:bg-raised ") +
        (pinned
          ? "text-[var(--color-brand-600)] hover:text-[var(--color-brand-700)]"
          : onCover
            ? "text-foreground/70 hover:text-foreground"
            : "text-muted-foreground/50 hover:text-foreground")
      }
    >
      <PinIcon className="text-[15px]" />
    </button>
  );
}

function SkillQuickAccess({
  pinned,
  recent,
  isPinned,
  onTogglePin,
}: {
  pinned: Skill[];
  recent: Skill[];
  isPinned: (skill: Skill) => boolean;
  onTogglePin: (skill: Skill) => void;
}) {
  return (
    <div className="mt-5 space-y-4">
      {pinned.length > 0 && (
        <QuickAccessRow title="Pinned">
          {pinned.map((skill) => (
            <SkillQuickCard
              key={`pin-${skill.folder_id}`}
              skill={skill}
              pinned
              onTogglePin={onTogglePin}
            />
          ))}
        </QuickAccessRow>
      )}
      {recent.length > 0 && (
        <QuickAccessRow title="Recent">
          {recent.map((skill) => (
            <SkillQuickCard
              key={`recent-${skill.folder_id}`}
              skill={skill}
              pinned={isPinned(skill)}
              onTogglePin={onTogglePin}
            />
          ))}
        </QuickAccessRow>
      )}
    </div>
  );
}

function QuickAccessRow({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="m-0 mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h2>
      <div className="flex flex-wrap gap-2.5">{children}</div>
    </section>
  );
}

function SkillQuickCard({
  skill,
  pinned,
  onTogglePin,
}: {
  skill: Skill;
  pinned: boolean;
  onTogglePin: (skill: Skill) => void;
}) {
  const dotColor = skill.published ? PUBLISH_COLOR.published : PUBLISH_COLOR.private;
  return (
    <Link
      href={skillHref(skill)}
      className="group/qa relative flex w-[200px] items-center gap-2.5 rounded-lg border border-border bg-surface px-3 py-2.5 transition hover:border-[var(--color-brand-300)] hover:bg-raised"
    >
      <span className="relative flex h-5 w-5 shrink-0 items-center justify-center text-[var(--color-brand-600)]">
        <SkillIcon className="text-[18px]" />
        {dotColor && (
          <span
            className="absolute -bottom-0.5 -right-0.5 h-[7px] w-[7px] rounded-full ring-2 ring-surface"
            style={{ background: dotColor }}
          />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] font-medium text-foreground">
          {skill.name}
        </span>
        <span className="block truncate text-[10.5px] text-muted-foreground">
          {skill.file_count} file{skill.file_count === 1 ? "" : "s"}
        </span>
      </span>
      <span className="shrink-0">
        <SkillPinButton pinned={pinned} onToggle={() => onTogglePin(skill)} />
      </span>
    </Link>
  );
}

function SkillViewToggle({
  view,
  onChange,
}: {
  view: ViewKey;
  onChange: (next: ViewKey) => void;
}) {
  const opts: { key: ViewKey; label: string }[] = [
    { key: "grid", label: "Grid" },
    { key: "list", label: "List" },
  ];
  return (
    <div className="inline-flex gap-0.5 rounded-md border border-border bg-base p-[2px] text-[12px]">
      {opts.map((opt) => {
        const active = view === opt.key;
        return (
          <button
            key={opt.key}
            type="button"
            onClick={() => onChange(opt.key)}
            className={
              "cursor-pointer rounded px-2 py-[3px] " +
              (active
                ? "bg-raised font-semibold text-foreground"
                : "text-muted-foreground hover:text-foreground")
            }
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}
