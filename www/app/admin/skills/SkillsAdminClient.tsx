"use client";

import Link from "next/link";
import { useActionState, useState, useTransition } from "react";

import { importRepo, removeRepo, type ActionResult } from "./actions";

export type ImportedRepo = {
  repo_url: string;
  skills: {
    title: string;
    slug: string;
    source_github_url: string;
    updated_at: string;
  }[];
};

export default function SkillsAdminClient({ repos }: { repos: ImportedRepo[] }) {
  const [importState, importAction, importing] = useActionState<ActionResult | null, FormData>(
    importRepo,
    null,
  );

  const total = repos.reduce((n, r) => n + r.skills.length, 0);

  return (
    <main className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex h-14 max-w-[1280px] items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-[15px] font-semibold text-gray-800">
              stash
            </Link>
            <span className="text-xs uppercase tracking-[0.14em] text-gray-400">
              Admin · Discover Skills
            </span>
          </div>
          <Link href="/admin/analytics" className="text-sm text-gray-500 hover:text-gray-800">
            Analytics →
          </Link>
        </div>
      </header>

      <section className="mx-auto max-w-[860px] px-6 py-8">
        <h1 className="text-2xl font-semibold text-gray-800">Discover Skills</h1>
        <p className="mt-1 text-sm text-gray-500">
          Import public GitHub repos into the Discover catalog. Every folder containing a
          SKILL.md becomes a discoverable skill. Re-importing a repo updates it in place.
        </p>

        <form action={importAction} className="mt-6 flex gap-2">
          <input
            name="repo_url"
            type="url"
            required
            placeholder="https://github.com/owner/repo"
            className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 outline-none focus:border-gray-500"
          />
          <button
            type="submit"
            disabled={importing}
            className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            {importing ? "Importing…" : "Import"}
          </button>
        </form>
        {importState && (
          <p
            className={`mt-2 text-sm ${importState.ok ? "text-green-700" : "text-red-600"}`}
          >
            {importState.message}
          </p>
        )}

        <div className="mt-8 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
            Imported repos
          </h2>
          <span className="text-xs text-gray-400">
            {repos.length} repo{repos.length === 1 ? "" : "s"} · {total} skill
            {total === 1 ? "" : "s"}
          </span>
        </div>

        {repos.length === 0 ? (
          <p className="mt-4 rounded-md border border-dashed border-gray-300 bg-white px-4 py-8 text-center text-sm text-gray-500">
            No GitHub skills imported yet.
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {repos.map((repo) => (
              <RepoRow key={repo.repo_url} repo={repo} />
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

function RepoRow({ repo }: { repo: ImportedRepo }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState("");
  const name = repo.repo_url.replace("https://github.com/", "");

  function onRemove() {
    if (!confirm(`Remove all ${repo.skills.length} skill(s) from ${name}?`)) return;
    setError("");
    startTransition(async () => {
      const result = await removeRepo(repo.repo_url);
      if (!result.ok) setError(result.message);
    });
  }

  return (
    <li className="rounded-md border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <a
          href={repo.repo_url}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-sm font-medium text-gray-800 hover:underline"
        >
          {name}
        </a>
        <button
          type="button"
          onClick={onRemove}
          disabled={pending}
          className="rounded-md border border-gray-300 px-3 py-1 text-xs font-medium text-gray-600 hover:border-red-400 hover:text-red-600 disabled:opacity-50"
        >
          {pending ? "Removing…" : "Remove"}
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {repo.skills.map((s) => (
          <a
            key={s.slug}
            href={`/skills/${s.slug}`}
            className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-200"
          >
            {s.title}
          </a>
        ))}
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </li>
  );
}
