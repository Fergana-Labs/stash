"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { displayVisibility } from "../../lib/api";

// Minimum shape required by the card — accepts both WorkspaceCartridge and
// PublicCartridgeCard so /discover and /workspaces/[id]/cartridges can share one
// component without dragging two type definitions into the union.
export interface CartridgeCardData {
  id: string;
  slug: string;
  title: string;
  description: string;
  cover_image_url: string | null;
  owner_name?: string;
  owner_display_name?: string | null;
  access?: "private" | "public";
  share_count?: number;
  is_external?: boolean;
  updated_at?: string;
  item_count?: number;
  items?: unknown[];
}

interface CartridgeCardProps {
  stash: CartridgeCardData;
  cover: string;
  /** Optional badge in the upper-left of the cover (e.g. trending, EXTERNAL). */
  badge?: ReactNode;
  /** Optional action in the upper-right of the cover (e.g. + Save button).
   * Action components own their own click-propagation handling. */
  cornerAction?: ReactNode;
  /** Custom footer; if omitted, defaults to `/{slug}` + relative-time. */
  footer?: ReactNode;
  /** Highlights the card when it's part of a multi-selection. */
  selected?: boolean;
}

const VIS_COLOR: Record<string, string> = {
  public: "#22C55E",
  shared: "var(--color-brand-500)",
  private: "#9CA3AF",
};

export default function CartridgeCard({
  stash,
  cover,
  badge,
  cornerAction,
  footer,
  selected,
}: CartridgeCardProps) {
  const itemCount = stash.item_count ?? stash.items?.length ?? 0;
  const visibility = stash.access
    ? displayVisibility(stash.access, stash.share_count ?? 0)
    : null;
  const dotColor = visibility ? VIS_COLOR[visibility] : null;
  const author = authorName(stash);

  return (
    <Link
      href={`/cartridges/${stash.slug}`}
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
          stash.cover_image_url
            ? {
                backgroundImage: `url(${stash.cover_image_url})`,
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
        {stash.is_external && !badge && (
          <span className="absolute left-3 top-2.5 rounded-full border border-white/50 bg-white/70 px-2 py-0.5 font-mono text-[10.5px] text-foreground backdrop-blur">
            EXTERNAL
          </span>
        )}
        {dotColor && (
          // Visibility lives as a small corner dot on the cover, freeing a
          // whole row of card body space the inline chip used to occupy.
          <span
            className="absolute bottom-2 left-2.5 inline-block h-[8px] w-[8px] rounded-full ring-2 ring-white/80"
            style={{ background: dotColor }}
            title={visibility ?? undefined}
          />
        )}
      </div>
      <div className="flex flex-1 flex-col p-4">
        <h3 className="m-0 font-display text-[17px] font-bold leading-tight tracking-[-0.015em] group-hover:text-[var(--color-brand-700)]">
          {stash.title}
        </h3>
        <p className="mt-2 line-clamp-2 text-[12.5px] leading-[1.55] text-dim">
          {stash.description || "No description."}
        </p>
        <div className="sys-label mt-2.5" style={{ fontSize: 10.5 }}>
          {author && `by ${author} · `}
          {itemCount} item{itemCount === 1 ? "" : "s"}
          {stash.updated_at && ` · updated ${relativeTime(stash.updated_at)}`}
        </div>
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

function authorName(stash: CartridgeCardData): string {
  return stash.owner_display_name || stash.owner_name || "";
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
