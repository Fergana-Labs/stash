"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import DeveloperGate from "@/components/developer/DeveloperGate";
import {
  Code,
  CodeBlock,
  PageHeading,
  SectionHeading,
} from "@/components/developer/DocsPrimitives";
import { getCurator, type CuratorRun, type OrgRef } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function CuratorRoute() {
  return (
    <DeveloperGate>
      <Curator />
    </DeveloperGate>
  );
}

type CuratorData = Awaited<ReturnType<typeof getCurator>>;

function Curator() {
  const [data, setData] = useState<CuratorData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);

  const refresh = useCallback(() => {
    setError(null);
    getCurator()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the curator"));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (error) {
    return <p className="text-[15px] text-error">Couldn&apos;t load the curator: {error}</p>;
  }
  if (!data) {
    return <p className="text-[15px] text-muted-foreground">Loading…</p>;
  }

  return (
    <>
      <PageHeading title="Curator">
        Every night it reads the sessions uploaded since it last ran and compiles them into two
        places: each org&apos;s own notepad, and the shared wiki every org&apos;s agent reads.
      </PageHeading>

      <section className="mb-12 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Fact label="Next run" value={formatWhen(data.next_run_at)} />
        <Fact label="Last run" value={formatWhen(data.curator.last_run_at)} />
        <Fact
          label="Reading since"
          value={formatWhen(data.curator.curated_through)}
          detail="Everything uploaded after this point is still uncurated."
        />
      </section>

      {data.curator.last_run_error && (
        <p className="mb-12 rounded border border-error/40 bg-error/5 px-5 py-4 text-[14px] text-error">
          Last run failed: {data.curator.last_run_error}
        </p>
      )}

      <section className="mb-12">
        <SectionHeading>Feeding the shared wiki</SectionHeading>
        <p className="mt-2 text-[13.5px] leading-6 text-muted-foreground">
          Every org gets its own notepad regardless. This is who also contributes to the
          anonymized wiki the others read.
        </p>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <OrgColumn
            title="Feeding"
            orgs={data.feeding}
            empty="No org is feeding the wiki, so it will stay as it is."
            accent
          />
          <OrgColumn
            title="Opted out"
            orgs={data.opted_out}
            empty="Every org is feeding the wiki."
          />
        </div>
      </section>

      <section className="mb-12">
        <div className="flex items-baseline justify-between gap-4">
          <SectionHeading>The prompt it will use</SectionHeading>
          <button
            onClick={() => setShowPrompt((open) => !open)}
            className="text-[13px] text-muted-foreground transition-colors hover:text-foreground"
          >
            {showPrompt ? "Hide" : "Show"}
          </button>
        </div>
        <p className="mt-2 text-[13.5px] leading-6 text-muted-foreground">
          Rendered from live state, so this is exactly what tonight&apos;s run sends — including
          the org list above and each org&apos;s wiki setting. Runs on{" "}
          <Code>{data.curator.schedule_cron}</Code> (UTC).
        </p>
        {showPrompt && (
          <div className="mt-4">
            <CodeBlock>{data.prompt}</CodeBlock>
          </div>
        )}
      </section>

      <section>
        <SectionHeading>Recent runs</SectionHeading>
        {data.runs.length === 0 ? (
          <p className="mt-4 rounded border border-dashed border-border px-6 py-8 text-center text-[14px] leading-6 text-muted-foreground">
            It hasn&apos;t run yet. The first run happens on the next nightly tick, once there are
            sessions to read.
          </p>
        ) : (
          <div className="mt-4 overflow-hidden rounded border border-border bg-surface">
            {data.runs.map((run) => (
              <Run key={run.session_id} run={run} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function Fact({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="rounded border border-border bg-surface px-5 py-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-2 text-[15px] text-foreground">{value}</div>
      {detail && <div className="mt-1 text-[12.5px] leading-5 text-muted-foreground">{detail}</div>}
    </div>
  );
}

function OrgColumn({
  title,
  orgs,
  empty,
  accent,
}: {
  title: string;
  orgs: OrgRef[];
  empty: string;
  accent?: boolean;
}) {
  return (
    <div className="overflow-hidden rounded border border-border bg-surface">
      <div className="flex items-baseline gap-2 border-b border-border px-5 py-3">
        <span className="text-[13px] font-medium text-foreground">{title}</span>
        <span
          className={cn(
            "font-mono text-[12px]",
            accent ? "text-brand-500" : "text-muted-foreground",
          )}
        >
          {orgs.length}
        </span>
      </div>
      {orgs.length === 0 ? (
        <p className="px-5 py-4 text-[13px] leading-5 text-muted-foreground">{empty}</p>
      ) : (
        orgs.map((org) => (
          <Link
            key={org.id}
            href={`/developer/orgs/${org.id}`}
            className="flex items-center gap-3 border-b border-border px-5 py-2.5 text-[14px] transition-colors last:border-b-0 hover:bg-raised"
          >
            <span className="min-w-0 flex-1 truncate text-foreground">{org.name}</span>
            <span className="shrink-0 font-mono text-[12px] text-muted-foreground">
              {org.external_id}
            </span>
          </Link>
        ))
      )}
    </div>
  );
}

const RUN_LABEL: Record<CuratorRun["status"], string> = {
  completed: "learned",
  failed: "failed",
  running: "running",
  stopped: "stopped",
  interrupted: "interrupted",
};

function Run({ run }: { run: CuratorRun }) {
  return (
    <div className="border-b border-border px-5 py-3.5 last:border-b-0">
      <div className="flex items-baseline gap-3">
        <span
          className={cn(
            "shrink-0 font-mono text-[11px] uppercase tracking-[0.1em]",
            run.status === "failed" ? "text-error" : "text-muted-foreground",
          )}
        >
          {RUN_LABEL[run.status]}
        </span>
        <span className="ml-auto shrink-0 font-mono text-[12px] text-muted-foreground">
          {formatWhen(run.started_at)}
        </span>
      </div>
      {run.summary && <p className="mt-1.5 text-[14px] leading-6 text-foreground">{run.summary}</p>}
      {run.error && <p className="mt-1.5 text-[13px] leading-5 text-error">{run.error}</p>}
    </div>
  );
}

function formatWhen(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
