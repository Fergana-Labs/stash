"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  askScopeStream,
  getMyTeam,
  getTeamAnalytics,
  getTeamMemoryTree,
  getTeamSkills,
  type Team,
  type TeamMemberStats,
  type TeamSkill,
  type TeamWikiFolder,
  type TeamWikiTree,
} from "@/lib/api";

function relative(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// The killer interaction: ask the team's shared brain, get a streamed
// answer grounded in the team scope's wiki, skills, and shared material.
function AskTeamBrain({ scopeUserId }: { scopeUserId: string }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");

  async function ask() {
    const prompt = question.trim();
    if (!prompt || asking) return;
    setAsking(true);
    setAnswer("");
    setError("");
    try {
      await askScopeStream(scopeUserId, prompt, (delta) =>
        setAnswer((prev) => prev + delta)
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ask failed");
    } finally {
      setAsking(false);
    }
  }

  return (
    <section className="rounded-2xl border border-border bg-surface p-6">
      <h2 className="text-base font-semibold text-foreground">
        Ask the team brain
      </h2>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Answers come from team memory — the wiki, skills, and what members
        have shared. Try &ldquo;how did we decide to enforce org
        isolation?&rdquo;
      </p>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask();
        }}
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask anything your team has worked on…"
          className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-brand-500/40"
        />
        <button
          type="submit"
          disabled={asking || !question.trim()}
          className="shrink-0 cursor-pointer rounded-lg bg-[var(--color-brand-600)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-60"
        >
          {asking ? "Thinking…" : "Ask"}
        </button>
      </form>
      {error && <p className="mt-2 text-xs text-error">{error}</p>}
      {answer && (
        <div className="mt-3 whitespace-pre-wrap rounded-lg bg-background p-4 text-sm text-foreground">
          {answer}
        </div>
      )}
    </section>
  );
}

function WikiPageList({ pages }: { pages: { id: string; name: string }[] }) {
  if (pages.length === 0) return null;
  return (
    <ul className="space-y-1">
      {pages.map((page) => (
        <li key={page.id}>
          <Link
            href={`/p/${page.id}`}
            className="text-sm text-foreground hover:underline"
          >
            {page.name.replace(/\.md$/, "")}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function WikiCategory({ folder }: { folder: TeamWikiFolder }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {folder.name}
      </h3>
      <div className="mt-1.5 space-y-4 pl-3 border-l border-border">
        <WikiPageList pages={folder.pages} />
        {folder.folders.map((child) => (
          <WikiCategory key={child.id} folder={child} />
        ))}
      </div>
    </div>
  );
}

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

// The team page: who's here, what the shared brain is built from, and
// usage analytics. Raw traces are never listed — teammates see a transcript
// only via an explicit per-person share. Analytics are metadata-only by
// design: counts and timestamps, never content.
export default function TeamPage() {
  const [team, setTeam] = useState<Team | null | undefined>(undefined);
  const [stats, setStats] = useState<TeamMemberStats[] | null>(null);
  const [wiki, setWiki] = useState<TeamWikiTree | null>(null);
  const [skills, setSkills] = useState<TeamSkill[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMyTeam()
      .then((result) => {
        setTeam(result);
        if (!result) return;
        getTeamAnalytics()
          .then((data) => setStats(data.members))
          .catch((e) => setError(e instanceof Error ? e.message : "Load failed"));
        getTeamMemoryTree(result.scope_user_id)
          .then(setWiki)
          .catch((e) => setError(e instanceof Error ? e.message : "Load failed"));
        getTeamSkills()
          .then((data) => setSkills(data.skills))
          .catch((e) => setError(e instanceof Error ? e.message : "Load failed"));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Load failed"));
  }, []);

  if (team === undefined) {
    return (
      <main className="flex-1 px-4 py-10">
        <p className="mx-auto max-w-3xl text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (team === null) {
    return (
      <main className="flex-1 px-4 py-10">
        <div className="mx-auto max-w-3xl space-y-2">
          <h1 className="text-2xl font-semibold text-foreground">Team</h1>
          <p className="text-sm text-muted-foreground">
            You&apos;re not in a workspace yet. Workspaces are created by the
            Stash team for your company domain — reach out and we&apos;ll set
            one up.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1 overflow-y-auto px-4 py-10">
      <div className="w-full max-w-3xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">{team.name}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {team.members.length} member{team.members.length === 1 ? "" : "s"} ·{" "}
            {team.domain}
          </p>
        </div>
        {error && <p className="text-xs text-error">{error}</p>}

        <AskTeamBrain scopeUserId={team.scope_user_id} />

        <section className="rounded-2xl border border-border bg-surface p-6">
          <h2 className="text-base font-semibold text-foreground">Team skills</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Procedural know-how distilled from at least two members&apos; work —
            the part of team knowledge agents should carry, not look up.
            (Auto-loading into agents is coming; for now they live here.)
          </p>
          <div className="mt-4">
            {skills === null ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : skills.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No skills yet — the curator distills them from members&apos;
                sessions.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {skills.map((skill) => (
                  <Link
                    key={skill.id}
                    href={`/p/${skill.id}`}
                    className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground hover:border-foreground/30"
                  >
                    {skill.name.replace(/\.md$/, "")}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-surface p-6">
          <h2 className="text-base font-semibold text-foreground">Team wiki</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Every member&apos;s sessions feed the team&apos;s wiki and skills
            by default — distilled and attributed, never the raw transcripts.
            Exclude any session from the{" "}
            <Link href="/activity" className="underline hover:text-foreground">
              command center
            </Link>{" "}
            or its own page. The curator runs nightly.
          </p>
          <div className="mt-4">
            {wiki === null ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : wiki.folders.length === 0 && wiki.pages.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No pages yet — the curator writes here after its first run.
              </p>
            ) : (
              <div className="space-y-4">
                <WikiPageList pages={wiki.pages} />
                {wiki.folders.map((folder) => (
                  <WikiCategory key={folder.id} folder={folder} />
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-surface p-6">
          <h2 className="text-base font-semibold text-foreground">Usage</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Per member — metadata only, never content. Token volume is
            estimated from transcript size.
          </p>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1.5 pr-4 font-medium">Member</th>
                  <th className="py-1.5 pr-4 font-medium text-right">7d</th>
                  <th className="py-1.5 pr-4 font-medium text-right">30d</th>
                  <th className="py-1.5 pr-4 font-medium text-right">Total</th>
                  <th className="py-1.5 pr-4 font-medium text-right">
                    ~Tokens (30d)
                  </th>
                  <th className="py-1.5 font-medium text-right">Last session</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {stats === null && (
                  <tr>
                    <td colSpan={6} className="py-3 text-muted-foreground">
                      Loading…
                    </td>
                  </tr>
                )}
                {stats?.map((member) => (
                  <tr key={member.id}>
                    <td className="py-2 pr-4 text-foreground">
                      {member.display_name}
                    </td>
                    <td className="py-2 pr-4 text-right">{member.sessions_7d}</td>
                    <td className="py-2 pr-4 text-right">{member.sessions_30d}</td>
                    <td className="py-2 pr-4 text-right">{member.sessions_total}</td>
                    <td className="py-2 pr-4 text-right">
                      {compact(member.est_tokens_30d)}
                    </td>
                    <td className="py-2 text-right text-muted-foreground">
                      {relative(member.last_session_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
