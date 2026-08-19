"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { BookOpen, Building2, KeyRound, MessagesSquare } from "lucide-react";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { listOrgs } from "@/lib/api";
import type { Org, Workspace } from "@/lib/types";

/**
 * Console Overview: the devtool landing. Stat tiles for what the platform has
 * absorbed, then the explore cards — the Supermemory-console shape from the
 * shaping doc's design inspiration.
 */
export default function DeveloperOverview() {
  return (
    <DeveloperGate>
      <Overview />
    </DeveloperGate>
  );
}

function Overview() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [stats, setStats] = useState({ wiki_page_count: 0, org_session_count: 0 });

  const refresh = useCallback(() => {
    listOrgs()
      .then((res) => {
        setWorkspace(res.workspace);
        setOrgs(res.orgs);
        setStats(res.stats);
      })
      .catch(() => setOrgs([]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!workspace) {
    return <div className="p-8 text-sm text-zinc-500">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8 p-8">
      <div>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="mt-1 text-sm text-zinc-500">{workspace.name}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Orgs" value={orgs.length} />
        <StatTile label="Org sessions" value={stats.org_session_count} />
        <StatTile label="Wiki pages" value={stats.wiki_page_count} />
        <StatTile
          label="Feeding the wiki"
          value={orgs.filter((o) => o.share_wiki).length}
        />
      </div>

      <section>
        <h2 className="mb-3 text-sm font-semibold">Explore the platform</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <ExploreCard
            href="/developer/keys"
            icon={<KeyRound className="h-4 w-4" />}
            title="Quick Setup"
            detail="Mint a key and wire the two-call contract"
          />
          <ExploreCard
            href="/developer/orgs"
            icon={<Building2 className="h-4 w-4" />}
            title="Orgs"
            detail="Your customers, their memory, wiki opt-outs"
          />
          <ExploreCard
            href="/developer/wiki"
            icon={<BookOpen className="h-4 w-4" />}
            title="Shared Wiki"
            detail="Anonymized knowledge read by every org"
          />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold">Recent orgs</h2>
        <div className="divide-y divide-zinc-200 rounded-lg border border-zinc-200 bg-white">
          {orgs.slice(0, 5).map((org) => (
            <div key={org.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
              <Building2 className="h-4 w-4 text-zinc-900" />
              <span className="font-medium">{org.name}</span>
              <span className="text-xs text-zinc-500">{org.external_id}</span>
              <span className="ml-auto flex items-center gap-1 text-xs text-zinc-500">
                <MessagesSquare className="h-3.5 w-3.5" />
                {org.session_count}
              </span>
            </div>
          ))}
          {orgs.length === 0 && (
            <div className="px-4 py-6 text-sm text-zinc-500">
              No orgs yet — they appear when your backend uploads a session with
              a new <code>org_id</code>. Start with{" "}
              <Link href="/developer/keys" className="text-zinc-900 underline">
                Quick Setup
              </Link>
              .
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="mt-1 font-mono text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function ExploreCard({
  href,
  icon,
  title,
  detail,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  detail: string;
}) {
  return (
    <Link
      href={href}
      className="rounded-lg border border-zinc-200 bg-white p-4 transition-colors hover:bg-zinc-50"
    >
      <div className="flex items-center gap-2 text-sm font-medium">
        <span className="text-zinc-900">{icon}</span>
        {title}
      </div>
      <div className="mt-1 text-xs text-zinc-500">{detail}</div>
    </Link>
  );
}
