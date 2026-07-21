"use client";

import Link from "next/link";
import type { ActivityEvent } from "../lib/api";
import { routes } from "@/lib/workspace-routes";
import { FileIcon, PageIcon, SessionsIcon } from "./SkillIcons";

const VERB: Record<string, string> = {
  "session.uploaded": "pushed a transcript",
  "page.updated": "edited a page",
  "file.uploaded": "uploaded a file",
};

const PALETTE = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-orange-200", fg: "text-orange-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-teal-200", fg: "text-teal-800" },
];

function colorFor(name: string) {
  let hash = 5381;
  for (let i = 0; i < name.length; i++) hash = (hash * 33 + name.charCodeAt(i)) >>> 0;
  return PALETTE[hash % PALETTE.length];
}

function targetHref(event: ActivityEvent): string | null {
  if (event.kind === "session.uploaded") {
    return routes.session(event.target_id);
  }
  if (event.kind === "page.updated") {
    return routes.page(event.target_id);
  }
  if (event.kind === "file.uploaded") {
    return routes.file(event.target_id);
  }
  return null;
}

function relative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function EventIcon({ kind }: { kind: string }) {
  if (kind === "session.uploaded") return <SessionsIcon />;
  if (kind === "page.updated") return <PageIcon />;
  if (kind === "file.uploaded") return <FileIcon />;
  return null;
}

export default function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  return (
    <div className="mt-6 flex flex-col">
      {events.map((event, index) => {
        const name = event.actor.display_name;
        const color = colorFor(name);
        const href = targetHref(event);

        return (
          <div
            key={`${event.kind}-${event.target_id}-${index}`}
            className="flex items-start gap-3 border-b border-border py-3 last:border-b-0"
          >
            <span
              className={
                "inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-semibold " +
                color.bg + " " + color.fg
              }
            >
              {name.slice(0, 2).toUpperCase()}
            </span>
            <div className="min-w-0 flex-1 text-[13px]">
              <span className="font-medium text-foreground">{name}</span>{" "}
              <span className="text-muted-foreground">{VERB[event.kind] || event.kind}</span>
              {event.target_label && href && (
                <>
                  {" "}
                  <Link
                    href={href}
                    className="font-medium text-foreground hover:text-[var(--color-brand-700)]"
                  >
                    <span className="inline-flex items-center gap-1">
                      <span className="inline-flex text-[15px] text-muted-foreground">
                        <EventIcon kind={event.kind} />
                      </span>
                      {event.target_label}
                    </span>
                  </Link>
                </>
              )}
              {event.target_label && !href && (
                <> <span className="text-foreground">{event.target_label}</span></>
              )}
              <div className="mt-0.5 text-[11px] text-muted-foreground">{relative(event.ts)}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
