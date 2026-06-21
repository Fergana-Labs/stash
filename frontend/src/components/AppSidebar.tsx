"use client";

import Link from "next/link";
import {
  useEffect,
  useMemo,
  useState,
  type MouseEvent,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import {
  getSidebar,
  listSources,
  type Sidebar,
  type Source,
} from "../lib/api";
import type { User } from "../lib/types";
import AddSourceModal from "./integrations/AddSourceModal";
import { connectorIcon, labelForProvider, providerForSourceType } from "./integrations/connectors";
import {
  ActivityIcon,
  FileIcon,
  HelpIcon,
  SessionsIcon,
  SettingsIcon,
  SkillIcon,
  TrashIcon,
} from "./SkillIcons";

interface AppSidebarProps {
  user?: User;
  onLogout?: () => void;
  cmdkOpen?: boolean;
  onCmdkOpen?: () => void;
}

const EXTERNAL_SOURCES_COLLAPSED_KEY = "stash_external_sources_collapsed";

// A colored dot per source type, so the grouped Sources list reads as a set of
// equal peers (matching the mockup). Falls back to neutral.
const SOURCE_DOT: Record<string, string> = {
  github_repo: "#111111",
  google_drive: "#16a34a",
  notion: "#000000",
  slack: "#4a154b",
  granola: "#e0700f",
  jira_project: "#2563eb",
  asana_project: "#f06a6a",
  gong_calls: "#7c3aed",
  snowflake: "#29b5e8",
  twitter: "#0f1419",
};

function NavRow({
  href,
  icon,
  label,
  active,
  onClick,
  onContextMenu,
  trailing,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
  onContextMenu?: (event: MouseEvent<HTMLAnchorElement>) => void;
  trailing?: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={
        "page-row group/nav flex min-w-0 items-center gap-1.5 rounded-md px-2 py-1 text-[13px] transition-colors " +
        (active
          ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)]"
          : "text-dim hover:bg-raised hover:text-foreground")
      }
      onClick={onClick}
      onContextMenu={onContextMenu}
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center text-[14px]">{icon}</span>
      <span className="min-w-0 flex-1 truncate" title={label}>{label}</span>
      {trailing}
    </Link>
  );
}

function SourceDot({ color }: { color: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 rounded-full"
      style={{ background: color }}
    />
  );
}

// A resolved row in the flat Sources list.
interface SourceRow {
  key: string;
  href: string;
  label: string;
  icon: ReactNode;
  active: boolean;
}

export default function AppSidebar({ user }: AppSidebarProps) {
  const pathname = usePathname();
  const userId = user?.id;
  const [addSourceOpen, setAddSourceOpen] = useState(false);
  const [sidebar, setSidebar] = useState<Sidebar | null>(null);
  // The viewer's connected external sources (GitHub/Drive/Gmail/Notion/Slack/...).
  const [sources, setSources] = useState<Source[]>([]);
  // Collapses only the connected external sources; the native Sessions,
  // Files, and Skills rows stay visible.
  const [externalCollapsed, setExternalCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(EXTERNAL_SOURCES_COLLAPSED_KEY) === "1";
  });

  function toggleExternalCollapsed() {
    const next = !externalCollapsed;
    setExternalCollapsed(next);
    localStorage.setItem(EXTERNAL_SOURCES_COLLAPSED_KEY, next ? "1" : "0");
  }

  // Load the viewer's sidebar (for the active-skill slug in Settings).
  useEffect(() => {
    if (!userId) return;
    getSidebar()
      .then(setSidebar)
      .catch(() => {});
  }, [userId]);

  // Load the viewer's connected sources for the Sources list.
  useEffect(() => {
    if (!userId) return;
    listSources()
      .then(setSources)
      .catch(() => {});
  }, [userId]);

  // The Sources list: the native sources always visible, then the user's
  // connected external sources behind a collapsible "External" header.
  // Connected sources are managed on the integrations settings page.
  const sourceRows = useMemo<{ native: SourceRow[]; connected: SourceRow[] }>(() => {
    const filesActive =
      !!pathname.match(/^\/(files|folders)(?:\/|$)/) ||
      !!pathname.match(/^\/(p|f)\//);
    const sessionsActive = pathname.startsWith("/sessions");
    const skillsActive = pathname.startsWith("/skills");
    const native: SourceRow[] = [
      {
        key: "sessions",
        href: "/sessions",
        label: "Agent Sessions",
        icon: <span className="text-muted"><SessionsIcon /></span>,
        active: sessionsActive,
      },
      {
        key: "files",
        href: "/files",
        label: "Files",
        icon: <span className="text-muted"><FileIcon /></span>,
        active: filesActive,
      },
      {
        key: "skills",
        href: "/skills",
        label: "Skills",
        icon: <span aria-hidden>❏</span>,
        active: skillsActive,
      },
    ];
    // One row per INTEGRATION (provider), not per source: collapse the
    // connected sources to their distinct providers. The dot color comes from
    // a representative source type of that provider.
    const seen = new Set<string>();
    const connected: SourceRow[] = [];
    for (const s of sources) {
      const provider = providerForSourceType[s.type] ?? s.type;
      if (seen.has(provider)) continue;
      seen.add(provider);
      const logo = connectorIcon(provider);
      connected.push({
        key: provider,
        href: `/integrations/${provider}`,
        label: labelForProvider(provider),
        icon: logo ? (
          <span className="flex h-4 w-4 items-center justify-center [&_img]:h-4 [&_img]:w-4 [&_svg]:h-4 [&_svg]:w-4">
            {logo}
          </span>
        ) : (
          <SourceDot color={SOURCE_DOT[s.type] ?? "rgba(0,0,0,0.4)"} />
        ),
        active: pathname.startsWith(`/integrations/${provider}`),
      });
    }
    return { native, connected };
  }, [sources, pathname]);

  const activeSkillSlug = pathname.match(/^\/skills\/([^/?#]+)/)?.[1] ?? null;
  const activeSkill = activeSkillSlug
    ? sidebar?.skills?.find((skill) => skill.published?.slug === activeSkillSlug)
    : null;
  // User settings live on the unified /settings page; only published Skills
  // keep their own settings route.
  const settingsHref = activeSkill?.published
    ? `/skills/${activeSkill.published.slug}/settings`
    : "/settings";
  const settingsActive = activeSkill?.published
    ? pathname === `/skills/${activeSkill.published.slug}/settings`
    : pathname === "/settings";

  return (
    <>
    <aside className="scroll-thin h-full overflow-y-auto border-r border-border bg-surface">
      <div className="px-3 pt-3 pb-1">
        <div className="truncate text-[14px] font-semibold text-foreground">
          {user?.display_name || user?.name || "You"}
        </div>
      </div>

      <nav className="px-2 pt-2 text-[13px]">
        <NavRow
          href="/"
          icon={<SkillIcon />}
          label="Home"
          active={pathname === "/"}
        />
        {/* "Index" is the revamped activity view — your accumulated
            knowledge, status, and newsfeed. Sits up top next to Home. */}
        <NavRow
          href="/activity"
          icon={<ActivityIcon />}
          label="Index"
          active={pathname.startsWith("/activity")}
        />
        <NavRow
          href="/agents"
          icon={<span aria-hidden>✦</span>}
          label="Agents"
          active={pathname.startsWith("/agents")}
        />
        <NavRow
          href="/discover"
          icon={<span aria-hidden>◎</span>}
          label="Discover"
          active={pathname.startsWith("/discover")}
        />
      </nav>

      <nav className="mt-4 px-2 text-[13px]">
        <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
          Your Brain
        </div>
        {sourceRows.native.map((row) => (
          <NavRow
            key={row.key}
            href={row.href}
            icon={row.icon}
            label={row.label}
            active={row.active}
          />
        ))}
      </nav>
      <nav className="mt-4 px-2 text-[13px]">
        <button
          type="button"
          onClick={toggleExternalCollapsed}
          className="flex w-full cursor-pointer items-center gap-1 px-2 pb-1 text-left text-[11px] font-semibold uppercase tracking-wide text-muted hover:text-foreground"
        >
          <span
            aria-hidden
            className={`transition-transform ${externalCollapsed ? "-rotate-90" : ""}`}
          >
            ▾
          </span>
          External Sources
        </button>
        {!externalCollapsed &&
          sourceRows.connected.map((row) => (
            <NavRow
              key={row.key}
              href={row.href}
              icon={row.icon}
              label={row.label}
              active={row.active}
            />
          ))}
        <button
          type="button"
          onClick={() => setAddSourceOpen(true)}
          className="page-row group/nav flex w-full min-w-0 cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-left text-[13px] text-dim transition-colors hover:bg-raised hover:text-foreground"
        >
          <span className="flex h-4 w-4 shrink-0 items-center justify-center text-[14px]" aria-hidden>
            ＋
          </span>
          <span className="min-w-0 flex-1 truncate">Add a new source</span>
        </button>
      </nav>

      <div className="mt-6 border-t border-border px-2 py-2">
        <NavRow
          href="/trash"
          icon={<TrashIcon />}
          label="Trash"
          active={pathname === "/trash"}
        />
        <a
          href="https://joinstash.ai/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="page-row group/nav flex min-w-0 items-center gap-1.5 rounded-md px-2 py-1 text-[13px] transition-colors text-dim hover:bg-raised hover:text-foreground"
        >
          <span className="flex h-4 w-4 shrink-0 items-center justify-center text-[14px]"><HelpIcon /></span>
          <span className="min-w-0 flex-1 truncate">Docs</span>
        </a>
        <NavRow
          href={settingsHref}
          icon={<SettingsIcon />}
          label="Settings"
          active={settingsActive}
        />
      </div>
    </aside>
    {addSourceOpen && (
      <AddSourceModal
        returnTo={pathname}
        onClose={() => setAddSourceOpen(false)}
      />
    )}
    </>
  );
}
