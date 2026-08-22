"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { PageHeading, SectionHeading } from "@/components/developer/DocsPrimitives";
import {
  listDeveloperFiles,
  type DeveloperFileRow,
  type DeveloperPageRow,
  type DeveloperUserFiles,
} from "@/lib/api";

export default function DeveloperFiles() {
  return (
    <DeveloperGate>
      <Files />
    </DeveloperGate>
  );
}

type FilesData = Awaited<ReturnType<typeof listDeveloperFiles>>;

/** The platform's files in the two piles they actually come in: what the
 *  shared wiki holds (every user's agent reads it), and what each user owns
 *  (their wiki pages and uploads — theirs alone). */
function Files() {
  const [data, setData] = useState<FilesData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listDeveloperFiles()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load files"));
  }, []);

  if (error) {
    return <p className="text-[15px] text-error">Couldn&apos;t load files: {error}</p>;
  }
  if (!data) {
    return <p className="text-[15px] text-muted-foreground">Loading…</p>;
  }

  return (
    <>
      <PageHeading title="Files">
        Two piles, two audiences: shared wiki files every user&apos;s agent reads, and each
        user&apos;s own files that only they (and you) can see.
      </PageHeading>

      <section className="mb-12">
        <div className="flex items-baseline justify-between gap-4">
          <SectionHeading>Shared wiki files</SectionHeading>
          <Link
            href="/developer/wiki"
            className="text-[13px] text-muted-foreground transition-colors hover:text-foreground"
          >
            Open the wiki
          </Link>
        </div>
        {data.wiki_pages.length === 0 && data.wiki_files.length === 0 ? (
          <Empty>
            Nothing yet. The curator writes here; you can also drop reference material into
            the wiki folder yourself and the next run folds it in.
          </Empty>
        ) : (
          <div className="mt-4 overflow-hidden rounded border border-border bg-surface">
            {data.wiki_pages.map((page) => (
              <PageLine key={page.id} page={page} />
            ))}
            {data.wiki_files.map((file) => (
              <FileLine key={file.id} file={file} />
            ))}
          </div>
        )}
      </section>

      <section>
        <SectionHeading>Per-user files</SectionHeading>
        {data.users.length === 0 ? (
          <Empty>No users yet, so no per-user files.</Empty>
        ) : (
          data.users.map((user) => <UserFiles key={user.id} user={user} />)
        )}
      </section>
    </>
  );
}

function UserFiles({ user }: { user: DeveloperUserFiles }) {
  const empty = user.notepad_pages.length === 0 && user.files.length === 0;
  return (
    <div className="mt-6">
      <Link
        href={`/developer/users/${user.id}`}
        className="inline-flex items-baseline gap-2 text-[14px] font-medium text-foreground hover:text-brand-500"
      >
        {user.name}
        <span className="font-mono text-[12px] font-normal text-muted-foreground">
          {user.external_id}
        </span>
      </Link>
      {empty ? (
        <p className="mt-2 text-[13px] leading-5 text-muted-foreground">
          Nothing yet — their wiki fills in on the curator&apos;s next run over their sessions.
        </p>
      ) : (
        <div className="mt-2 overflow-hidden rounded border border-border bg-surface">
          {user.notepad_pages.map((page) => (
            <PageLine key={page.id} page={page} />
          ))}
          {user.files.map((file) => (
            <FileLine key={file.id} file={file} />
          ))}
        </div>
      )}
    </div>
  );
}

function PageLine({ page }: { page: DeveloperPageRow }) {
  return (
    <Link
      href={`/p/${page.id}`}
      className="flex items-center gap-4 border-b border-border px-5 py-3 transition-colors last:border-b-0 hover:bg-raised"
    >
      <span className="min-w-0 flex-1 truncate text-[14px] text-foreground">{page.name}</span>
      <span className="shrink-0 font-mono text-[12px] text-muted-foreground">
        page · {formatDate(page.updated_at)}
      </span>
    </Link>
  );
}

function FileLine({ file }: { file: DeveloperFileRow }) {
  return (
    <Link
      href={`/f/${file.id}`}
      className="flex items-center gap-4 border-b border-border px-5 py-3 transition-colors last:border-b-0 hover:bg-raised"
    >
      <span className="min-w-0 flex-1 truncate text-[14px] text-foreground">{file.name}</span>
      <span className="shrink-0 font-mono text-[12px] text-muted-foreground">
        {formatBytes(file.size_bytes)} · {formatDate(file.created_at)}
      </span>
    </Link>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-4 rounded border border-dashed border-border px-6 py-8 text-center text-[14px] leading-6 text-muted-foreground">
      {children}
    </p>
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
