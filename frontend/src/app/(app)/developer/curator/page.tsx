"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import DeveloperGate from "@/components/developer/DeveloperGate";
import {
  CodeBlock,
  PageHeading,
  SectionHeading,
} from "@/components/developer/DocsPrimitives";
import {
  backfillCurator,
  getCurator,
  runCuratorNow,
  updateCuratorInstructions,
  type CuratorRun,
  type EndUserRef,
} from "@/lib/api";
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
        One agent for the whole workspace, one run a night. It reads only the sessions
        uploaded since its last run — cost scales with new conversation, not with how many
        users you have — and in that single run writes both places at once: each active
        user&apos;s own wiki, and the shared anonymized wiki every user&apos;s agent reads.
      </PageHeading>

      <section className="mb-12 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Fact
          label="Next run"
          value={formatWhen(data.next_run_at)}
          detail={describeSchedule(data.curator.schedule_cron)}
        />
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
        <SectionHeading>When does the curator run?</SectionHeading>
        <div className="mt-4 overflow-hidden rounded border border-border bg-surface">
          <table className="w-full text-left text-[13.5px]">
            <thead>
              <tr className="border-b border-border font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <th className="px-5 py-3 font-normal">Trigger</th>
                <th className="px-5 py-3 font-normal">When</th>
                <th className="px-5 py-3 font-normal">What it reads</th>
              </tr>
            </thead>
            <tbody className="text-foreground">
              <ScheduleRow
                trigger="Nightly"
                when={`${describeSchedule(data.curator.schedule_cron)} — a fixed slot picked for your workspace`}
                reads="Everything uploaded since its last run"
              />
              <ScheduleRow
                trigger="First day"
                when="After every conversation uploaded during your workspace's first 24 hours"
                reads="Everything uploaded since its last run"
              />
              <ScheduleRow
                trigger="Run now"
                when="Immediately — the button under Recent runs below"
                reads="Everything uploaded since its last run"
              />
              <ScheduleRow
                trigger="Backfill"
                when="Immediately, after you confirm it"
                reads="The full history, watermark cleared"
              />
            </tbody>
          </table>
        </div>
      </section>

      <section className="mb-12">
        <SectionHeading>Feeding the shared wiki</SectionHeading>
        <p className="mt-2 text-[13.5px] leading-6 text-muted-foreground">
          Every user gets their own wiki regardless. This is who also contributes to the
          anonymized wiki the others read.
        </p>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <UserColumn
            title="Feeding"
            users={data.feeding}
            empty="No user is feeding the wiki, so it will stay as it is."
            accent
          />
          <UserColumn
            title="Opted out"
            users={data.opted_out}
            empty="Every user is feeding the wiki."
          />
        </div>
      </section>

      <Instructions initial={data.instructions} />

      <PromptSection nightly={data.prompt} backfill={data.backfill_prompt} />

      <Runs runs={data.runs} onStarted={refresh} />
    </>
  );
}

/** The tunable part of the prompt. The rendered prompt below is built from
 *  live state on every run, so it can't be edited directly — these
 *  instructions are the developer's hook into it. */
function Instructions({ initial }: { initial: string | null }) {
  const [text, setText] = useState(initial ?? "");
  const [saved, setSaved] = useState(initial ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const res = await updateCuratorInstructions(text.trim());
      setSaved(res.instructions ?? "");
      setText(res.instructions ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the instructions");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="mb-12">
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading>Your instructions</SectionHeading>
        {text.trim() !== saved && (
          <button
            onClick={() => void save()}
            disabled={saving}
            className="rounded-sm bg-brand-500 px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        )}
      </div>
      <p className="mt-2 text-[13.5px] leading-6 text-muted-foreground">
        Appended to the curator&apos;s prompt on every run — nightly, run-now, and backfill.
        Use it to steer what gets curated: what belongs in the shared wiki, what should stay
        per-user, what to ignore entirely.
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        placeholder={
          "e.g. Part cross-references and diagnostic procedures belong in the shared wiki. " +
          "Pricing a user was quoted is per-user only, never shared."
        }
        className="mt-4 w-full rounded border border-border bg-surface px-4 py-3 text-[14px] leading-6 text-foreground placeholder:text-muted-foreground focus:border-brand-500 focus:outline-none"
      />
      {error && <p className="mt-2 text-[13px] text-error">{error}</p>}
    </section>
  );
}

function PromptSection({ nightly, backfill }: { nightly: string; backfill: string }) {
  const [shown, setShown] = useState<"hidden" | "nightly" | "backfill">("hidden");
  return (
    <section className="mb-12">
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading>Prompt</SectionHeading>
        <div className="flex items-center gap-3 text-[13px]">
          <PromptTab shown={shown} value="nightly" onShow={setShown}>
            Nightly
          </PromptTab>
          <PromptTab shown={shown} value="backfill" onShow={setShown}>
            Backfill
          </PromptTab>
        </div>
      </div>
      <p className="mt-2 text-[13.5px] leading-6 text-muted-foreground">
        Rendered from live state, so this is exactly what the run sends. The nightly prompt
        names only the users with something new since the watermark — a user who has said
        nothing cannot have anything curated for them, and naming every user would grow the
        prompt with your customer base rather than with the work in front of it. The
        backfill prompt is the same thing with no watermark: the full history.
      </p>
      {shown !== "hidden" && (
        <div className="mt-4">
          <CodeBlock>{shown === "nightly" ? nightly : backfill}</CodeBlock>
        </div>
      )}
    </section>
  );
}

function PromptTab({
  shown,
  value,
  onShow,
  children,
}: {
  shown: string;
  value: "nightly" | "backfill";
  onShow: (v: "hidden" | "nightly" | "backfill") => void;
  children: React.ReactNode;
}) {
  const active = shown === value;
  return (
    <button
      onClick={() => onShow(active ? "hidden" : value)}
      className={cn(
        "transition-colors",
        active ? "font-medium text-brand-500" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function Runs({ runs, onStarted }: { runs: CuratorRun[]; onStarted: () => void }) {
  const [running, setRunning] = useState(false);
  const [armingBackfill, setArmingBackfill] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  async function start(action: () => Promise<unknown>) {
    setRunning(true);
    setRunError(null);
    try {
      await action();
      // The run happens on the worker; the entry appears when it writes.
      setTimeout(onStarted, 4000);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Could not start the run");
    } finally {
      setRunning(false);
      setArmingBackfill(false);
    }
  }

  return (
    <section>
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading>Recent runs</SectionHeading>
        <div className="flex items-center gap-2">
          {armingBackfill ? (
            <>
              <span className="text-[12.5px] text-muted-foreground">
                Re-reads the full history and updates pages in place.
              </span>
              <button
                onClick={() => void start(backfillCurator)}
                disabled={running}
                className="rounded-sm bg-brand-500 px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-50"
              >
                {running ? "Starting…" : "Confirm backfill"}
              </button>
              <button
                onClick={() => setArmingBackfill(false)}
                disabled={running}
                className="rounded-sm border border-border px-3 py-1.5 text-[13px] text-dim transition-colors hover:bg-raised"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setArmingBackfill(true)}
                disabled={running}
                className="rounded-sm border border-border px-3 py-1.5 text-[13px] text-dim transition-colors hover:bg-raised hover:text-foreground disabled:opacity-50"
              >
                Backfill
              </button>
              <button
                onClick={() => void start(runCuratorNow)}
                disabled={running}
                className="rounded-sm bg-brand-500 px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-50"
              >
                {running ? "Starting…" : "Run now"}
              </button>
            </>
          )}
        </div>
      </div>
      <p className="mt-2 text-[13.5px] leading-6 text-muted-foreground">
        Run now curates what&apos;s new since the watermark. Backfill clears the watermark and
        re-reads the full history — after a bulk upload, or to rebuild the wikis under new
        instructions. Pages update in place either way.
      </p>
      {runError && <p className="mt-2 text-[13px] text-error">{runError}</p>}
      {runs.length === 0 ? (
        <p className="mt-4 rounded border border-dashed border-border px-6 py-8 text-center text-[14px] leading-6 text-muted-foreground">
          It hasn&apos;t run yet. The first run happens on the next nightly tick, once there
          are sessions to read — or run it now.
        </p>
      ) : (
        <div className="mt-4 overflow-hidden rounded border border-border bg-surface">
          {runs.map((run) => (
            <Run key={run.session_id} run={run} />
          ))}
        </div>
      )}
    </section>
  );
}

function ScheduleRow({ trigger, when, reads }: { trigger: string; when: string; reads: string }) {
  return (
    <tr className="border-b border-border last:border-b-0">
      <td className="whitespace-nowrap px-5 py-3 align-top font-medium">{trigger}</td>
      <td className="px-5 py-3 align-top leading-5">{when}</td>
      <td className="px-5 py-3 align-top leading-5 text-muted-foreground">{reads}</td>
    </tr>
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

function UserColumn({
  title,
  users,
  empty,
  accent,
}: {
  title: string;
  users: EndUserRef[];
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
          {users.length}
        </span>
      </div>
      {users.length === 0 ? (
        <p className="px-5 py-4 text-[13px] leading-5 text-muted-foreground">{empty}</p>
      ) : (
        users.map((user) => (
          <Link
            key={user.id}
            href={`/developer/users/${user.id}`}
            className="flex items-center gap-3 border-b border-border px-5 py-2.5 text-[14px] transition-colors last:border-b-0 hover:bg-raised"
          >
            <span className="min-w-0 flex-1 truncate text-foreground">{user.name}</span>
            <span className="shrink-0 font-mono text-[12px] text-muted-foreground">
              {user.external_id}
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
  skipped: "skipped",
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
        <Link
          href={`/sessions/${encodeURIComponent(run.session_id)}`}
          className="shrink-0 font-mono text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        >
          transcript
        </Link>
        <span className="ml-auto shrink-0 font-mono text-[12px] text-muted-foreground">
          {formatWhen(run.started_at)}
        </span>
      </div>
      {run.summary && <p className="mt-1.5 text-[14px] leading-6 text-foreground">{run.summary}</p>}
      {run.error && <p className="mt-1.5 text-[13px] leading-5 text-error">{run.error}</p>}
    </div>
  );
}

// The curator's cron is generated as a staggered nightly slot ("M H * * *") so
// every workspace runs at its own minute. Say that in words — a crontab string
// is not an answer to "when does this run".
function describeSchedule(cron: string): string {
  const nightly = /^(\d{1,2}) (\d{1,2}) \* \* \*$/.exec(cron.trim());
  if (!nightly) return `Runs on ${cron} (UTC)`;
  const [, minute, hour] = nightly;
  return `Every night at ${hour.padStart(2, "0")}:${minute.padStart(2, "0")} UTC`;
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
