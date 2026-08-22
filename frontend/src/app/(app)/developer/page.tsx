"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

import DeveloperGate from "@/components/developer/DeveloperGate";
import UserTable from "@/components/developer/UserTable";
import { Code, PageHeading, SectionHeading } from "@/components/developer/DocsPrimitives";
import { listUsers } from "@/lib/api";
import type { EndUser, Workspace } from "@/lib/types";

export default function DeveloperOverview() {
  return (
    <DeveloperGate>
      <Overview />
    </DeveloperGate>
  );
}

// Setup steps, in the order a developer does them. Bordered rows rather than
// www/DESIGN.md's numbered hairline list: that move is for claims you read,
// and these are things you click.
const ROUTES = [
  {
    href: "/developer/keys",
    title: "Mint a key, wire two calls",
    detail: "Upload each turn with a user_id, read back with the same one.",
  },
  {
    href: "/developer/users",
    title: "Your product's users",
    detail: "A private wiki each, and who feeds the shared wiki.",
  },
  {
    href: "/developer/wiki",
    title: "The anonymized shared wiki",
    detail: "What every user's agent reads, with no user named.",
  },
];

function Overview() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [users, setUsers] = useState<EndUser[]>([]);
  const [stats, setStats] = useState({ wiki_page_count: 0, user_session_count: 0 });
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setError(null);
    listUsers()
      .then((res) => {
        setWorkspace(res.workspace);
        setUsers(res.users);
        setStats(res.stats);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the console"));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (error) {
    return <p className="text-[15px] text-error">Couldn&apos;t load the console: {error}</p>;
  }

  if (!workspace) {
    return <p className="text-[15px] text-muted-foreground">Loading…</p>;
  }

  return (
    <>
      <PageHeading title="Overview">{workspace.name}</PageHeading>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Users" value={users.length} />
        <Stat label="User sessions" value={stats.user_session_count} />
        <Stat label="Wiki pages" value={stats.wiki_page_count} />
        <Stat label="Feeding the wiki" value={users.filter((o) => o.share_wiki).length} />
      </div>

      <section className="mt-12">
        <SectionHeading>Set up</SectionHeading>
        <div className="mt-4 space-y-2">
          {ROUTES.map((route, i) => (
            <Link
              key={route.href}
              href={route.href}
              className="group flex items-center gap-4 rounded border border-border bg-surface px-5 py-4 transition-colors hover:border-brand-300 hover:bg-raised"
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-500/10 font-mono text-[12px] text-brand-500">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-medium text-foreground">
                  {route.title}
                </span>
                <span className="mt-0.5 block text-[13.5px] leading-6 text-muted-foreground">
                  {route.detail}
                </span>
              </span>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-brand-500" />
            </Link>
          ))}
        </div>
      </section>

      <section className="mt-14">
        <SectionHeading>Recent users</SectionHeading>
        {users.length === 0 ? (
          <p className="mt-3 text-[15px] leading-7 text-dim">
            No users yet — they appear when your backend uploads a session with a new{" "}
            <Code>user_id</Code>. Start with{" "}
            <Link href="/developer/keys" className="text-brand-500 underline underline-offset-2">
              API Keys
            </Link>
            .
          </p>
        ) : (
          <div className="mt-4">
            <UserTable users={users.slice(0, 5)} onChanged={refresh} />
          </div>
        )}
      </section>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-border bg-surface px-5 py-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-2 font-display text-[28px] font-medium tabular-nums text-foreground">
        {value}
      </div>
    </div>
  );
}
