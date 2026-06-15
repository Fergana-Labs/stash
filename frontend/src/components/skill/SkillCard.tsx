"use client";

import Link from "next/link";
import type { ReactNode } from "react";

// Minimum shape required by the card — both workspace skill folders and the
// Discover catalog's PublicSkillCard project into this.
export interface SkillCardData {
  title: string;
  description: string;
  cover_image_url: string | null;
  icon_url?: string | null;
  owner_name?: string;
  owner_display_name?: string | null;
  /** Publish state badge: pass null for Private, undefined to hide the badge. */
  published?: { discoverable: boolean } | null;
  updated_at?: string;
  file_count?: number;
}

interface SkillCardProps {
  skill: SkillCardData;
  href: string;
  cover: string;
  /** Optional badge in the upper-left of the cover (e.g. trending). */
  badge?: ReactNode;
  /** Optional action in the upper-right of the cover (e.g. + Save button).
   * Action components own their own click-propagation handling. */
  cornerAction?: ReactNode;
  /** Custom footer; if omitted, no footer renders. */
  footer?: ReactNode;
  /** Highlights the card when it's part of a multi-selection. */
  selected?: boolean;
}

export const PUBLISH_COLOR = {
  published: "#22C55E",
  discover: "var(--color-brand-500)",
  private: "#9CA3AF",
} as const;

// The one way publish state is shown on a Skill: a dot + label pill. Used on
// card covers and list rows — every row says Published / Private itself, with
// a second dot when the skill is also listed on Discover.
export function PublishBadge({
  published,
}: {
  published: { discoverable: boolean } | null;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-base px-1.5 py-0.5 text-[10.5px] text-muted">
      <span
        className="inline-block h-[7px] w-[7px] rounded-full"
        style={{
          background: published ? PUBLISH_COLOR.published : PUBLISH_COLOR.private,
        }}
      />
      {published ? "Published" : "Private"}
      {published?.discoverable && (
        <span
          title="Listed on Discover"
          className="inline-block h-[7px] w-[7px] rounded-full"
          style={{ background: PUBLISH_COLOR.discover }}
        />
      )}
    </span>
  );
}

export default function SkillCard({
  skill,
  href,
  cover,
  badge,
  cornerAction,
  footer,
  selected,
}: SkillCardProps) {
  const author = authorName(skill);
  const metaParts = [
    author && `by ${author}`,
    skill.file_count !== undefined &&
      `${skill.file_count} file${skill.file_count === 1 ? "" : "s"}`,
    skill.updated_at && `updated ${relativeTime(skill.updated_at)}`,
  ].filter(Boolean) as string[];

  return (
    <Link
      href={href}
      className={
        "card group flex min-h-[200px] flex-col overflow-hidden transition " +
        (selected
          ? "ring-2 ring-[var(--color-brand-400)]"
          : "hover:border-[var(--color-brand-300)]")
      }
    >
      <div
        className={`${cover} relative h-[84px]`}
        style={
          skill.cover_image_url
            ? {
                backgroundImage: `url(${skill.cover_image_url})`,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }
            : undefined
        }
      >
        {badge}
        {cornerAction && (
          <div className="absolute right-2.5 top-2 z-10">{cornerAction}</div>
        )}
        {skill.published !== undefined && (
          <span className="absolute bottom-2 left-2.5">
            <PublishBadge published={skill.published} />
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col p-4">
        <div className="flex items-center gap-2">
          {skill.icon_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={skill.icon_url}
              alt=""
              className="h-5 w-5 flex-shrink-0 rounded object-cover"
            />
          )}
          <h3 className="m-0 font-display text-[17px] font-bold leading-tight tracking-[-0.015em] group-hover:text-[var(--color-brand-700)]">
            {skill.title}
          </h3>
        </div>
        <p className="mt-2 line-clamp-2 text-[12.5px] leading-[1.55] text-dim">
          {skill.description || "No description."}
        </p>
        {metaParts.length > 0 && (
          <div className="sys-label mt-2.5" style={{ fontSize: 10.5 }}>
            {metaParts.join(" · ")}
          </div>
        )}
        <div className="flex-1" />
        {footer && (
          <div className="mt-3.5 flex items-center justify-between gap-2 border-t border-border-subtle pt-2.5 text-[11.5px] text-muted">
            {footer}
          </div>
        )}
      </div>
    </Link>
  );
}

function authorName(skill: SkillCardData): string {
  return skill.owner_display_name || skill.owner_name || "";
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
