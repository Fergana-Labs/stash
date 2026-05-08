"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import AppShell from "../../../../../components/AppShell";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { useAuth } from "../../../../../hooks/useAuth";
import { getStashSkill, getWorkspace, type StashSkillDetail } from "../../../../../lib/api";
import type { Workspace } from "../../../../../lib/types";

interface Frontmatter {
  raw: string;
  fields: Record<string, string>;
}

function splitFrontmatter(md: string): { fm: Frontmatter | null; body: string } {
  if (!md.startsWith("---")) return { fm: null, body: md };
  const end = md.indexOf("\n---", 3);
  if (end < 0) return { fm: null, body: md };
  const raw = md.slice(0, end + 4);
  const fields: Record<string, string> = {};
  raw
    .replace(/^---\n?|\n?---$/g, "")
    .split("\n")
    .forEach((line) => {
      const i = line.indexOf(":");
      if (i > 0) fields[line.slice(0, i).trim()] = line.slice(i + 1).trim();
    });
  const body = md.slice(end + 4).replace(/^\n+/, "");
  return { fm: { raw, fields }, body };
}

export default function SkillPage() {
  const params = useParams();
  const router = useRouter();
  const stashId = params.stashId as string;
  const name = decodeURIComponent(params.name as string);
  const { user, loading, logout } = useAuth();

  const [stash, setStash] = useState<Workspace | null>(null);
  const [skill, setSkill] = useState<StashSkillDetail | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useBreadcrumbs(
    [{ label: "Skills" }, { label: `/${name}` }],
    `${stashId}/skill/${name}`
  );

  const load = useCallback(async () => {
    try {
      setStash(await getWorkspace(stashId));
      setSkill(await getStashSkill(stashId, name));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load skill");
    }
  }, [stashId, name]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const { fm, body } = useMemo(() => {
    const md = skill?.files.find((f) => f.name === "SKILL.md")
      ? skill?.combined?.split("\n\n## ")[0] ?? ""
      : "";
    // Reconstruct: combined starts with "# {name} (SKILL.md)\n\n{body}".
    // We want the original SKILL.md frontmatter + body. The skill_service
    // strips frontmatter into `body`, so combined doesn't include the YAML.
    // Render the description + when_to_use as a synthesized frontmatter card.
    return splitFrontmatter(md);
  }, [skill]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  // Synthesize a frontmatter view from the skill metadata fields.
  const frontmatter = skill
    ? [
        ["name", skill.name],
        ["description", skill.description],
        ["when_to_use", skill.when_to_use],
      ]
        .filter(([, v]) => v)
        .map(([k, v]) => `${k}: ${v}`)
        .join("\n")
    : "";

  // The skill body ALREADY had its frontmatter stripped server-side. We
  // render that body directly with a real markdown renderer; the YAML is
  // shown as its own code block above so readers see what an agent sees.
  const renderedBody = skill?.body || body || "";
  const supportingFiles = skill?.files.filter((f) => f.name !== "SKILL.md") ?? [];
  void fm; // (the in-body frontmatter parser is here for future use)

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-5xl gap-10 px-12 py-10 lg:grid-cols-[1fr_220px]">
          <div className="min-w-0">
          <div className="mb-2 flex items-center gap-2 text-[12px] uppercase tracking-wider text-[var(--color-brand-700)]">
            <span>⚡</span> Skill
            <span className="text-muted">·</span>
            <span className="italic text-muted">procedural memory</span>
          </div>

          <h1 className="font-display text-[36px] font-bold tracking-tight text-foreground">
            /{skill?.name || name}
          </h1>
          {skill?.description && (
            <p className="mt-1 text-[15px] text-muted">{skill.description}</p>
          )}

          {error && (
            <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          {frontmatter && (
            <pre className="mt-5 overflow-auto rounded-md border border-border bg-surface px-4 py-3 font-mono text-[12px] leading-relaxed text-foreground">
              <span className="text-muted">---</span>
              {"\n"}
              {frontmatter}
              {"\n"}
              <span className="text-muted">---</span>
            </pre>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              onClick={async () => {
                if (!skill) return;
                await navigator.clipboard.writeText(skill.combined);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
              className="rounded-md border border-border bg-base px-3 py-1.5 text-[12px] text-foreground hover:border-[var(--color-brand-400)] hover:text-[var(--color-brand-700)]"
            >
              {copied ? "Copied" : "Copy as markdown"}
            </button>
            <span className="text-[11px] text-muted">
              Drop into any agent&apos;s skills directory.
            </span>
          </div>

          <article className="markdown-content mt-8 text-[14.5px] leading-relaxed text-foreground">
            {renderedBody ? (
              <Markdown remarkPlugins={[remarkGfm]}>{renderedBody}</Markdown>
            ) : (
              <p className="text-muted">{skill ? "Empty skill body." : "Loading…"}</p>
            )}
          </article>

          </div>

          {/* Right rail: files in this skill */}
          <aside className="hidden lg:block">
            <div className="sticky top-4 rounded-xl border border-border bg-surface p-4">
              <div className="mb-2 text-[10.5px] font-semibold uppercase tracking-wider text-muted">
                Files in this skill
              </div>
              <ul className="flex flex-col gap-1 text-[12.5px]">
                {(skill?.files ?? []).map((f) => {
                  const isSkillMd = f.name === "SKILL.md";
                  const icon = isSkillMd ? "📄" : f.name.endsWith(".md") ? "📋" : "📄";
                  return (
                    <li
                      key={f.id}
                      className={
                        "flex items-center gap-1.5 rounded-md px-2 py-1 " +
                        (isSkillMd
                          ? "bg-base text-foreground ring-1 ring-border"
                          : "text-dim hover:bg-base hover:text-foreground")
                      }
                    >
                      <span>{icon}</span>
                      <span className="truncate">{f.name}</span>
                    </li>
                  );
                })}
                {!skill && <li className="px-2 py-1 italic text-muted">Loading…</li>}
              </ul>
              <div className="mt-3 border-t border-border pt-3 text-[10.5px] uppercase tracking-wide text-muted">
                MCP exposed
              </div>
              <div className="mt-1 font-mono text-[11px] text-foreground">
                stash_read_skill(&quot;{skill?.name || name}&quot;)
              </div>
            </div>
          </aside>
          {/* Mobile: render the same list inline below the body */}
          {supportingFiles.length > 0 && (
            <div className="border-t border-border pt-6 lg:hidden">
              <div className="mb-3 text-[10.5px] font-semibold uppercase tracking-wider text-muted">
                Supporting files
              </div>
              <div className="flex flex-col gap-2">
                {supportingFiles.map((f) => (
                  <div
                    key={f.id}
                    className="rounded-lg border border-border bg-base px-3 py-2 text-[13px]"
                  >
                    📄 {f.name}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
