"use client";

import Link from "next/link";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";

import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import DescriptionEditor, {
  isBlankDescription,
} from "../../../../components/DescriptionEditor";
import {
  useActiveWorkspaceId,
  useShareAction,
} from "../../../../components/ShellChromeContext";
import { PublicSkillSkeleton } from "../../../../components/SkeletonStates";
import ResourceShareButton from "../../../../components/share/ResourceShareButton";
import SkillShareButton from "../../../../components/skill/SkillShareButton";
import { SettingsIcon, SkillIcon } from "../../../../components/SkillIcons";
import { useAuth } from "../../../../hooks/useAuth";
import {
  ApiError,
  getPublicSkill,
  updateSkill,
  uploadFile,
  type PublicSkillContents,
  type PublicSkillDetail,
  type SkillPublishInfo,
} from "../../../../lib/api";
import { SKILL_MD, stripFrontmatter } from "../../../../lib/localSkill";
import AddToWorkspaceButton from "./AddToWorkspaceButton";

export default function SkillPageClient({ slug }: { slug: string }) {
  const { user } = useAuth();
  const [data, setData] = useState<PublicSkillDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getPublicSkill(slug));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setData(null);
        setError("Skill not found");
      } else {
        setError(e instanceof Error ? e.message : "Failed to load Skill");
      }
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load]);

  useBreadcrumbs(
    [
      { label: "Skills", href: "/skills" },
      { label: data?.skill.title ?? "Skill" },
    ],
    `skill/${data?.skill.id ?? "loading"}`,
  );
  useActiveWorkspaceId(data?.skill.workspace_id ?? null);

  // Memo so the registered ReactNode is stable across renders — otherwise the
  // shell-chrome context would loop (AppShell re-renders → SkillPageClient
  // re-renders → new node identity → setShareAction → AppShell re-renders).
  const skill = data?.skill ?? null;
  const canWrite = data?.can_write ?? false;
  const shareAction = useMemo(() => {
    if (!skill || !canWrite) return null;
    const publish: SkillPublishInfo = {
      id: skill.id,
      slug: skill.slug,
      discoverable: skill.discoverable,
      cover_image_url: skill.cover_image_url,
      icon_url: skill.icon_url,
      view_count: skill.view_count,
    };
    return (
      <div className="flex items-center gap-1.5">
        {/* Person-to-person sharing of a skill = sharing its folder. */}
        {user && (
          <ResourceShareButton
            objectType="folder"
            objectId={skill.folder_id}
            resourceName={skill.title}
            resourceUrlPath={`/workspaces/${skill.workspace_id}/skills/${skill.folder_id}`}
            currentUser={user}
          />
        )}
        <SkillShareButton
          workspaceId={skill.workspace_id}
          folderId={skill.folder_id}
          publish={publish}
          onPublishChange={() => void load()}
        />
      </div>
    );
  }, [skill, canWrite, user, load]);
  useShareAction(shareAction);

  if (loading) {
    return <PublicSkillSkeleton />;
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <h1 className="font-display text-[28px] font-bold text-foreground">
          Skill not found
        </h1>
        <p className="mt-2 text-[14px] leading-relaxed text-dim">
          {error ||
            "This skill is private, revoked, or unavailable to the current user."}
        </p>
      </div>
    );
  }

  return <SkillPageBody data={data} onRefresh={load} />;
}

// Stable cover gradient per skill, mirroring the cover-1..6 utilities used
// elsewhere in the design. djb2-ish hash → bucket index so the same skill
// always gets the same cover.
function coverIndexFor(id: string): number {
  let h = 5381;
  for (let i = 0; i < id.length; i++) h = (h * 33 + id.charCodeAt(i)) >>> 0;
  return h % 6;
}

const COVER_GRADIENTS = [
  "linear-gradient(135deg, #FED7AA, #FCA5A5)",
  "linear-gradient(135deg, #BFDBFE, #A7F3D0)",
  "linear-gradient(135deg, #A7F3D0, #BAE6FD)",
  "linear-gradient(135deg, #FDE68A, #FECACA)",
  "linear-gradient(135deg, #BAE6FD, #FED7AA)",
  "linear-gradient(135deg, #FECDD3, #FEF3C7)",
];

// The SKILL.md at the skill root is the intro; everything else lists as rows.
function skillMdPage(contents: PublicSkillContents) {
  return (
    contents.pages.find((p) => p.name === SKILL_MD && p.folder_path.length === 0) ??
    null
  );
}

type ContentRow = {
  key: string;
  href: string;
  name: string;
  sub: string;
  kind: "page" | "file" | "table";
  folderPath: string[];
};

function contentRows(contents: PublicSkillContents, slug: string): ContentRow[] {
  const skillParam = encodeURIComponent(slug);
  const intro = skillMdPage(contents);
  const rows: ContentRow[] = [];
  for (const page of contents.pages) {
    if (intro && page.id === intro.id) continue;
    rows.push({
      key: `page-${page.id}`,
      href: `/p/${page.id}?skill=${skillParam}`,
      name: page.name,
      sub: page.content_type === "html" ? "html page" : "page",
      kind: "page",
      folderPath: page.folder_path,
    });
  }
  for (const file of contents.files) {
    rows.push({
      key: `file-${file.id}`,
      href: `/f/${file.id}?skill=${skillParam}`,
      name: file.name,
      sub: file.content_type || "file",
      kind: "file",
      folderPath: file.folder_path,
    });
  }
  for (const table of contents.tables) {
    rows.push({
      key: `table-${table.id}`,
      href: `/tables/${table.id}?skill=${skillParam}`,
      name: table.name,
      sub: `table · ${table.rows.length} row${table.rows.length === 1 ? "" : "s"}`,
      kind: "table",
      folderPath: table.folder_path,
    });
  }
  return rows;
}

function SkillPageBody({
  data,
  onRefresh,
}: {
  data: PublicSkillDetail;
  onRefresh: () => Promise<void>;
}) {
  const { skill, workspace_name, contents, can_write } = data;

  const cover = skill.cover_image_url
    ? { backgroundImage: `url(${skill.cover_image_url})` }
    : { backgroundImage: COVER_GRADIENTS[coverIndexFor(skill.id)] };

  const author = skill.owner_display_name || skill.owner_name;
  const intro = skillMdPage(contents);
  const rows = contentRows(contents, skill.slug);
  // Group rows by their subfolder path; root items first.
  const groups = new Map<string, ContentRow[]>();
  for (const row of rows) {
    const key = row.folderPath.join(" / ");
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  const groupKeys = [...groups.keys()].sort((a, b) =>
    a === "" ? -1 : b === "" ? 1 : a.localeCompare(b),
  );

  return (
    <div className="scroll-thin min-h-screen bg-background">
      {/* Cover banner — click to upload (when can_write). Mirrors the
          workspace home identity strip but with edit affordance. */}
      <BannerImage
        cover={cover}
        canWrite={can_write}
        workspaceId={skill.workspace_id}
        skillId={skill.id}
        hasCustomCover={!!skill.cover_image_url}
        onChanged={onRefresh}
      />

      <div className="mx-auto max-w-[920px] px-12 pb-20">
        {/* Identity strip: icon overlaps banner, title + meta + actions. */}
        <div className="flex items-start justify-between gap-3 pt-4">
          <div className="flex min-w-0 items-center gap-3">
            <SkillIconUpload
              iconUrl={skill.icon_url}
              canWrite={can_write}
              workspaceId={skill.workspace_id}
              skillId={skill.id}
              onChanged={onRefresh}
            />
            <div className="min-w-0">
              <h1 className="m-0 truncate font-display text-[20px] font-bold leading-tight tracking-[-0.015em] text-foreground">
                {skill.title}
              </h1>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-muted">
                <span>by {author}</span>
                <span className="text-muted/60">·</span>
                <span>
                  {rows.length} file{rows.length === 1 ? "" : "s"}
                </span>
                {skill.updated_at && (
                  <>
                    <span className="text-muted/60">·</span>
                    <span>updated {relativeTime(skill.updated_at)}</span>
                  </>
                )}
                {workspace_name && (
                  <>
                    <span className="text-muted/60">·</span>
                    <span className="truncate">in {workspace_name}</span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex flex-shrink-0 items-center gap-1.5 pt-1">
            {can_write ? (
              <Link
                href={`/skills/${skill.slug}/settings`}
                title="Skill settings"
                aria-label="Skill settings"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-raised hover:text-foreground"
              >
                <SettingsIcon />
              </Link>
            ) : (
              // Forking only makes sense when the viewer doesn't already have
              // write access to this skill in its own workspace.
              <AddToWorkspaceButton
                slug={skill.slug}
                sourceWorkspaceId={skill.workspace_id}
              />
            )}
          </div>
        </div>

        <SkillDescriptionEditor
          skillId={skill.id}
          workspaceId={skill.workspace_id}
          description={skill.description}
          canEdit={can_write}
          onSaved={() => {
            void onRefresh();
          }}
        />

        {intro && (
          <section className="mt-6">
            <div className="markdown-content">
              <Markdown remarkPlugins={[remarkGfm]}>
                {stripFrontmatter(intro.content_markdown || "")}
              </Markdown>
            </div>
          </section>
        )}

        <div className="mt-6 flex flex-col gap-5">
          {groupKeys.map((key) => (
            <section key={key || "root"}>
              {key && (
                <div className="mb-2 flex items-baseline gap-2 border-b border-border-subtle pb-1.5">
                  <h2 className="m-0 font-display text-[15px] font-semibold text-foreground">
                    {key}
                  </h2>
                </div>
              )}
              <div className="flex flex-col gap-1">
                {groups.get(key)!.map((row) => (
                  <ContentRowLink key={row.key} row={row} />
                ))}
              </div>
            </section>
          ))}
          {rows.length === 0 && !intro && (
            <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[13px] text-muted">
              Nothing here yet.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ContentRowLink({ row }: { row: ContentRow }) {
  return (
    <Link
      href={row.href}
      className="flex items-center gap-2.5 rounded-md px-2 py-1.5 hover:bg-raised"
    >
      <span
        className={
          "flex h-5 w-5 flex-shrink-0 items-center justify-center " +
          (row.kind === "table" ? "text-emerald-600" : "text-muted")
        }
      >
        <KindGlyph kind={row.kind} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13.5px] font-medium text-foreground">
          {row.name || "(untitled)"}
        </span>
        <span className="block truncate text-[11.5px] text-muted">{row.sub}</span>
      </span>
      <span className="hidden text-[11.5px] text-muted sm:inline">Open →</span>
    </Link>
  );
}

// Clickable banner. Writers see a faint "Change banner" hint on hover and
// can upload a new image via the hidden file input. Uploads go through
// the workspace's file upload path; the resulting URL is saved on the
// skill record.
function BannerImage({
  cover,
  canWrite,
  workspaceId,
  skillId,
  hasCustomCover,
  onChanged,
}: {
  cover: { backgroundImage: string };
  canWrite: boolean;
  workspaceId: string;
  skillId: string;
  hasCustomCover: boolean;
  onChanged: () => Promise<void>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (inputRef.current) inputRef.current.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const uploaded = await uploadFile(workspaceId, file);
      await updateSkill(skillId, { cover_image_url: uploaded.url });
      await onChanged();
    } finally {
      setUploading(false);
    }
  }

  if (!canWrite) {
    return <div className="h-[72px] w-full bg-cover bg-center" style={cover} />;
  }

  return (
    <div
      className="group relative h-[72px] w-full cursor-pointer bg-cover bg-center"
      style={cover}
      onClick={() => inputRef.current?.click()}
      title="Change banner"
    >
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition group-hover:bg-black/25 group-hover:opacity-100">
        <span className="rounded-md bg-black/60 px-2 py-1 text-[11.5px] font-medium text-white">
          {uploading
            ? "Uploading…"
            : hasCustomCover
              ? "Change banner"
              : "Add banner"}
        </span>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleChange}
      />
    </div>
  );
}

// Icon (logo) shown overlapping the banner. Writers can click to upload.
function SkillIconUpload({
  iconUrl,
  canWrite,
  workspaceId,
  skillId,
  onChanged,
}: {
  iconUrl: string | null;
  canWrite: boolean;
  workspaceId: string;
  skillId: string;
  onChanged: () => Promise<void>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (inputRef.current) inputRef.current.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const uploaded = await uploadFile(workspaceId, file);
      await updateSkill(skillId, { icon_url: uploaded.url });
      await onChanged();
    } finally {
      setUploading(false);
    }
  }

  const base =
    "-mt-9 flex h-12 w-12 flex-shrink-0 items-center justify-center overflow-hidden rounded-[10px] border-2 border-base bg-base text-[var(--color-brand-700)] shadow-sm";

  const inner = iconUrl ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={iconUrl} alt="" className="h-full w-full object-cover" />
  ) : (
    <SkillIcon className="text-[24px]" />
  );

  if (!canWrite) {
    return <span className={base}>{inner}</span>;
  }

  return (
    <button
      type="button"
      onClick={() => inputRef.current?.click()}
      title="Change logo"
      className={
        base +
        " group relative cursor-pointer p-0 hover:ring-2 hover:ring-[var(--color-brand-300)]"
      }
    >
      {inner}
      <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/0 text-[10px] font-medium text-white opacity-0 transition group-hover:bg-black/40 group-hover:opacity-100">
        {uploading ? "…" : "Change"}
      </span>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleChange}
      />
    </button>
  );
}

function SkillDescriptionEditor({
  skillId,
  workspaceId,
  description,
  canEdit,
  onSaved,
}: {
  skillId: string;
  workspaceId: string;
  description: string;
  canEdit: boolean;
  onSaved: () => void;
}) {
  if (!canEdit && isBlankDescription(description)) return null;

  return (
    <section className="mt-5">
      <DescriptionEditor
        value={description}
        canEdit={canEdit}
        placeholder="Describe this skill…"
        ariaLabel="Skill description"
        workspaceId={workspaceId}
        onSave={async (html) => {
          await updateSkill(skillId, { description: html });
          onSaved();
        }}
      />
    </section>
  );
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} d ago`;
  return new Date(iso).toLocaleDateString();
}

function KindGlyph({ kind }: { kind: "page" | "file" | "table" }) {
  if (kind === "table")
    return (
      <svg
        viewBox="0 0 24 24"
        width="14"
        height="14"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 10h18M3 16h18M9 4v16M15 4v16" />
      </svg>
    );
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
    >
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}
