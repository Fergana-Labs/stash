"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import ActivityFeed from "../../../components/ActivityFeed";
import MembersModal from "../../../components/MembersModal";
import {
  StashIcon,
} from "../../../components/StashIcons";
import { useAuth } from "../../../hooks/useAuth";
import {
  getWorkspace,
  getWorkspaceMembers,
  getWorkspaceOverview,
  joinWorkspace,
  listStashes,
  listWorkspaceActivity,
  updateWorkspace,
  type ActivityEvent,
  type WorkspaceOverview,
  type WorkspaceStash,
} from "../../../lib/api";
import { useShareModal } from "../../../lib/shareModalContext";
import type { Workspace, WorkspaceMember } from "../../../lib/types";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Heading from "@tiptap/extension-heading";
import Bold from "@tiptap/extension-bold";
import Italic from "@tiptap/extension-italic";
import TiptapLink from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";

export default function WorkspaceHomePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading } = useAuth();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [stashes, setStashes] = useState<WorkspaceStash[]>([]);
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [error, setError] = useState("");
  const [membersOpen, setMembersOpen] = useState(false);
  const shareModal = useShareModal();
  const shareVersion = shareModal.version;

  const load = useCallback(async () => {
    const [workspaceResult, membersResult, stashesResult, overviewResult, activityResult] =
      await Promise.allSettled([
        getWorkspace(workspaceId),
        getWorkspaceMembers(workspaceId),
        listStashes(workspaceId),
        getWorkspaceOverview(workspaceId),
        listWorkspaceActivity(workspaceId, 12),
      ]);

    if (workspaceResult.status === "fulfilled") {
      setWorkspace(workspaceResult.value);
    } else {
      setError("Workspace not found");
    }

    if (membersResult.status === "fulfilled") {
      setMembers(membersResult.value);
    }

    if (stashesResult.status === "fulfilled") {
      setStashes(stashesResult.value);
    }
    if (overviewResult.status === "fulfilled") {
      setOverview(overviewResult.value);
    }
    if (activityResult.status === "fulfilled") {
      setActivity(activityResult.value);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (!user) return;
    load();
  }, [user, load, shareVersion]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const isMember = !!user && members.some((m) => m.user_id === user.id);
  const recentSessions = useMemo(() => overview?.sessions.slice(0, 6) ?? [], [overview]);
  const newsfeedStashes = useMemo(
    () =>
      [...stashes]
        .sort((a, b) => {
          if (a.discoverable !== b.discoverable) return a.discoverable ? -1 : 1;
          return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        })
        .slice(0, 6),
    [stashes]
  );

  async function handleJoin() {
    if (!workspace) return;
    try {
      await joinWorkspace(workspace.invite_code);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to join");
    }
  }

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  return (
    <>
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div
          className="h-32 bg-gradient-to-r from-[var(--color-brand-200)] via-amber-100 to-rose-100 bg-cover bg-center"
          style={
            workspace?.cover_image_url
              ? { backgroundImage: `url(${workspace.cover_image_url})` }
              : workspace?.color_gradient
              ? { backgroundImage: workspace.color_gradient }
              : undefined
          }
        />
        <div className="mx-auto -mt-8 max-w-3xl px-12 pb-16">
          <div className="mb-2 flex h-12 w-12 items-center justify-center overflow-hidden text-5xl text-[var(--color-brand-700)]">
            {workspace?.icon_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={workspace.icon_url} alt="" className="h-12 w-12 rounded-lg object-cover" />
            ) : (
              <StashIcon />
            )}
          </div>
          <div className="flex items-center gap-2">
            <h1 className="font-display text-[34px] font-bold tracking-tight text-foreground">
              {workspace?.name || "Loading…"}
            </h1>
            {isMember && (
              <Link
                href={`/workspaces/${workspaceId}/settings`}
                title="Workspace settings"
                className="rounded-md p-1.5 text-muted hover:bg-raised hover:text-foreground"
                aria-label="Settings"
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
              </Link>
            )}
          </div>


          <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-muted">
            <button
              onClick={() => setMembersOpen(true)}
              title="View, add, or remove members"
              className="rounded-md px-1.5 py-0.5 hover:bg-raised"
            >
              <MemberStack members={members} />
              <span className="ml-1.5 text-[11px] underline-offset-2 hover:underline">
                Members
              </span>
            </button>
            <span className="text-muted">·</span>
            <button
              onClick={() =>
                shareModal.open({
                  workspaceId,
                  workspaceName: workspace?.name,
                  tab: stashes.length > 0 ? "manage" : "new",
                })
              }
              title="View, create, or revoke stashes"
              className="rounded-md px-1.5 py-0.5 hover:bg-raised"
            >
              <span aria-hidden>🔗</span>{" "}
              {stashes.length === 0
                ? "No Stashes"
                : `${stashes.length} Stash${stashes.length === 1 ? "" : "es"}`}
            </button>
            <span className="text-muted">·</span>
            <span>updated {workspace?.updated_at ? formatRelative(workspace.updated_at) : ""}</span>
          </div>

          {error && (
            <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          {!isMember && workspace && (
            <div className="mt-4 flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 text-[13px]">
              <span className="text-muted">You aren&apos;t a member of this workspace.</span>
              <button
                onClick={handleJoin}
                className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
              >
                Join workspace
              </button>
            </div>
          )}

          <WorkspaceNewsfeed
            workspaceId={workspaceId}
            sessions={recentSessions}
            stashes={newsfeedStashes}
            activity={activity}
          />

          <div className="mt-10 border-t border-border-subtle pt-8">
            <h2 className="mb-3 font-display text-[20px] font-semibold text-foreground">
              About this workspace
            </h2>
            <WorkspaceDescriptionEditor
              workspace={workspace}
              canEdit={isMember}
              onSaved={(updated) => setWorkspace(updated)}
            />
          </div>
        </div>
      </div>
      <MembersModal workspaceId={workspaceId} open={membersOpen} onClose={() => setMembersOpen(false)} />
    </>
  );
}


const AVATAR_PALETTE: { bg: string; fg: string }[] = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-indigo-200", fg: "text-indigo-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-fuchsia-200", fg: "text-fuchsia-800" },
];

function roleLabel(role: string): string {
  if (role === "owner") return "admin";
  return role;
}

type NewsfeedSession = WorkspaceOverview["sessions"][number];

function WorkspaceNewsfeed({
  workspaceId,
  sessions,
  stashes,
  activity,
}: {
  workspaceId: string;
  sessions: NewsfeedSession[];
  stashes: WorkspaceStash[];
  activity: ActivityEvent[];
}) {
  return (
    <section className="mt-8">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            Newsfeed
          </p>
          <h2 className="mt-1 font-display text-[22px] font-semibold text-foreground">
            Recent work
          </h2>
        </div>
        <Link
          href={`/activity?workspace=${workspaceId}`}
          className="rounded-md border border-border-subtle px-2.5 py-1.5 text-[12px] text-muted hover:border-brand hover:text-brand"
        >
          Activity
        </Link>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(260px,0.85fr)]">
        <div className="space-y-5">
          <NewsfeedPanel title="Recent sessions">
            {sessions.length === 0 ? (
              <EmptyNewsfeedLine text="No sessions yet." />
            ) : (
              <div className="flex flex-col gap-2">
                {sessions.map((session) => (
                  <Link
                    key={session.session_id}
                    href={`/workspaces/${workspaceId}/sessions/${encodeURIComponent(session.session_id)}`}
                    className="rounded-lg border border-border-subtle bg-base px-3 py-2.5 hover:border-brand hover:bg-[var(--color-brand-50)]"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-[13px] font-medium text-foreground">
                          {session.title || session.session_id}
                        </div>
                        <div className="mt-1 text-[11px] text-muted">
                          {session.agent_name || "agent"} · {formatRelative(session.last_at)}
                        </div>
                      </div>
                      <span className="shrink-0 font-mono text-[10px] uppercase text-muted">
                        Session
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </NewsfeedPanel>

          <NewsfeedPanel title="Stashes">
            {stashes.length === 0 ? (
              <EmptyNewsfeedLine text="No Stashes yet." />
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {stashes.map((stash) => (
                  <Link
                    key={`${stash.added_to_workspace_id ?? stash.workspace_id}:${stash.id}`}
                    href={`/stashes/${stash.slug}`}
                    className="rounded-lg border border-border-subtle bg-base px-3 py-2.5 hover:border-brand hover:bg-[var(--color-brand-50)]"
                  >
                    <div className="truncate text-[13px] font-medium text-foreground">
                      {stash.title}
                    </div>
                    <div className="mt-1 text-[11px] text-muted">
                      {stash.discoverable ? "Discover · " : ""}
                      {stash.is_external ? "External · " : ""}
                      {stash.items.length} item{stash.items.length === 1 ? "" : "s"}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </NewsfeedPanel>
        </div>

        <NewsfeedPanel title="Activity">
          {activity.length === 0 ? (
            <EmptyNewsfeedLine text="No activity yet." />
          ) : (
            <ActivityFeed events={activity} />
          )}
        </NewsfeedPanel>
      </div>
    </section>
  );
}

function NewsfeedPanel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section>
      <h3 className="mb-2 font-display text-[15px] font-semibold text-foreground">{title}</h3>
      <div className="rounded-lg border border-border bg-surface p-3">{children}</div>
    </section>
  );
}

function EmptyNewsfeedLine({ text }: { text: string }) {
  return <p className="px-1 py-2 text-[13px] text-muted">{text}</p>;
}

function avatarFor(name: string) {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function MemberStack({ members }: { members: WorkspaceMember[] }) {
  if (!members.length) return null;
  const display = members.slice(0, 5);
  const overflow = members.length - display.length;
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex -space-x-1.5">
        {display.map((m) => {
          const label = (m.display_name || m.name || "?").trim();
          const palette = avatarFor(label);
          return (
            <span
              key={m.user_id}
              className={
                "inline-flex h-5 w-5 items-center justify-center rounded-full border-2 border-base text-[9.5px] font-semibold " +
                palette.bg +
                " " +
                palette.fg
              }
              title={`${label}${m.role && m.role !== "editor" ? ` · ${roleLabel(m.role)}` : ""}`}
            >
              {label.slice(0, 2).toUpperCase()}
            </span>
          );
        })}
      </div>
      {overflow > 0 && <span className="text-[11px] text-muted">+{overflow}</span>}
      <span className="text-[12px] text-muted">
        {members.length} member{members.length !== 1 ? "s" : ""}
      </span>
    </div>
  );
}

function formatRelative(iso: string): string {
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


const AUTOSAVE_MS = 1500;

function WorkspaceDescriptionEditor({
  workspace,
  canEdit,
  onSaved,
}: {
  workspace: Workspace | null;
  canEdit: boolean;
  onSaved: (updated: Workspace) => void;
}) {
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaved = useRef<string>("");

  const description = workspace?.description ?? "";

  useEffect(() => {
    lastSaved.current = description;
  }, [description]);

  const editor = useEditor({
    immediatelyRender: false,
    editable: canEdit,
    content: description || "<p></p>",
    extensions: [
      StarterKit.configure({
        blockquote: false,
        codeBlock: false,
        heading: false,
        bold: false,
        italic: false,
        link: false,
        underline: false,
      }),
      Heading.configure({ levels: [1, 2, 3] }),
      Bold,
      Italic,
      TiptapLink.configure({ openOnClick: true, autolink: true }),
      Placeholder.configure({
        placeholder: "Describe this workspace…",
      }),
    ],
    editorProps: {
      attributes: {
        class: "min-h-[120px] focus:outline-none file-page-body",
      },
    },
    onUpdate: ({ editor: ed }) => {
      if (!workspace) return;
      const html = ed.getHTML();
      if (html === lastSaved.current) return;
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        lastSaved.current = html;
        const updated = await updateWorkspace(workspace.id, { description: html });
        onSaved(updated);
      }, AUTOSAVE_MS);
    },
  });

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  if (!workspace) return null;

  if (!canEdit && !description) return null;

  return (
    <div className="file-page-content">
      <EditorContent editor={editor} />
    </div>
  );
}
