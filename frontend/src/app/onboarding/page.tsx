"use client";

import { Suspense, useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { track } from "../../lib/analytics";
import { createPage, getToken, listMyWorkspaces, updateMe } from "../../lib/api";
import { generateCollabIntroMarkdown } from "../../lib/onboarding/collabIntro";
import { seedWelcomePage } from "../../lib/onboarding/seedWelcome";
import SourceConnectorList from "../../components/integrations/SourceConnectorList";

import MemoryAskStep from "./paths/memory/MemoryAskStep";

// The linear flow: a few questions about the user, explain Stash, connect a
// source, then ask the agent a real question over your data, then launch.
const STEP_NAMES = ["about", "intro", "connect", "ask"] as const;

const ROLE_OPTIONS = [
  "Engineer",
  "Eng Manager",
  "Founder / Exec",
  "Product",
  "Designer",
  "Researcher",
  "Other",
];

const REFERRAL_OPTIONS = [
  "Search",
  "X / Twitter",
  "Friend or colleague",
  "GitHub",
  "LinkedIn",
  "Other",
];

function useStashToken(): string | null {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener("storage", cb);
      return () => window.removeEventListener("storage", cb);
    },
    () => getToken(),
    () => null,
  );
}

export default function OnboardingPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-muted">Loading…</div>
      }
    >
      <OnboardingInner />
    </Suspense>
  );
}

function OnboardingInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading, logout } = useAuth();
  const apiKey = useStashToken();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [sourceCount, setSourceCount] = useState(0);
  const [obsidianAdded, setObsidianAdded] = useState(false);
  const [answered, setAnswered] = useState(false);
  const [role, setRole] = useState("");
  const [referralSource, setReferralSource] = useState("");
  const [useCase, setUseCase] = useState("");

  const stepIdx = useMemo(() => {
    const raw = searchParams.get("step");
    const parsed = raw ? parseInt(raw, 10) : 1;
    return Number.isFinite(parsed) && parsed > 0 ? parsed - 1 : 0;
  }, [searchParams]);

  useEffect(() => {
    if (!loading && apiKey === null) router.replace("/login");
  }, [loading, apiKey, router]);

  useEffect(() => {
    if (!apiKey) return;
    listMyWorkspaces()
      .then(({ workspaces }) => {
        const primary = workspaces.find((workspace) => workspace.is_primary) ?? workspaces[0];
        if (primary) setWorkspaceId(primary.id);
      })
      .catch(() => {});
  }, [apiKey]);

  useEffect(() => {
    if (loading || !apiKey) return;
    track("onboarding.viewed", { has_path: false });
  }, [loading, apiKey]);

  useEffect(() => {
    const name = STEP_NAMES[stepIdx];
    if (name) track("onboarding.step_viewed", { step_idx: stepIdx, step_name: name });
  }, [stepIdx]);

  const goToStep = useCallback(
    (idx: number) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("step", String(idx + 1));
      router.push(`/onboarding?${params.toString()}`);
    },
    [router, searchParams],
  );

  const exitToWorkspace = useCallback(() => {
    if (workspaceId) router.push(`/workspaces/${workspaceId}`);
    else router.push("/");
  }, [router, workspaceId]);

  const finishAndExit = useCallback(async () => {
    track("onboarding.completed", { total_steps: STEP_NAMES.length });
    if (workspaceId && user) {
      try {
        await seedWelcomePage({
          workspaceId,
          displayName: user.display_name || user.name,
        });
      } catch {
        // Best-effort — the user can edit the workspace description anytime.
      }
    }
    exitToWorkspace();
  }, [workspaceId, user, exitToWorkspace]);

  const skip = useCallback(() => {
    track("onboarding.skipped", { step_idx: stepIdx });
    exitToWorkspace();
  }, [exitToWorkspace, stepIdx]);

  // The "I just want to write with my agent" path: skip connecting sources,
  // seed a starter page, and drop the user straight into the collaborative
  // editor. This is the Google-Docs-for-agents wedge, so it bypasses the ask step.
  const finishToCollabDoc = useCallback(async () => {
    if (!workspaceId) return;
    track("onboarding.collab_path_chosen", {});
    const content = generateCollabIntroMarkdown(user?.display_name || user?.name || "");
    const page = await createPage(workspaceId, "Welcome to your Drive", undefined, content);
    router.push(`/workspaces/${workspaceId}/p/${page.id}`);
  }, [workspaceId, user, router]);

  if (loading || !apiKey) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">Loading…</div>
    );
  }

  // 0 = about, 1 = intro, 2 = connect, 3 = ask.
  const isAbout = stepIdx <= 0;
  const isIntro = stepIdx === 1;
  const isConnect = stepIdx === 2;
  const isAsk = stepIdx >= 3;

  const continueLabel = isIntro
    ? "Get started"
    : isAsk
      ? "Launch workspace"
      : "Continue";
  // About: role + referral are required (use-case is optional). Ask: only let
  // them launch once the agent has actually replied.
  const canContinue = isAbout
    ? Boolean(role && referralSource)
    : isIntro || (isAsk ? answered : sourceCount > 0 || obsidianAdded);
  const onContinue = async () => {
    if (isAbout) {
      try {
        await updateMe({
          role,
          referral_source: referralSource,
          use_case: useCase || undefined,
        });
      } catch {
        // Best-effort — don't block onboarding on a profile write.
      }
      track("onboarding.about_submitted", { role, referral_source: referralSource });
      return goToStep(stepIdx + 1);
    }
    if (isAsk) return void finishAndExit();
    goToStep(stepIdx + 1);
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 px-4 py-10">
        <div className="mx-auto w-full max-w-2xl space-y-8">
          <ProgressBar stepIdx={stepIdx} />
          {isAbout && (
            <AboutStep
              role={role}
              referralSource={referralSource}
              useCase={useCase}
              onRole={setRole}
              onReferral={setReferralSource}
              onUseCase={setUseCase}
            />
          )}
          {isIntro && <IntroStep />}
          {isConnect && (
            <ConnectStep
              workspaceId={workspaceId}
              onSourceCountChange={setSourceCount}
              onObsidianAdded={() => setObsidianAdded(true)}
              onCollabDoc={finishToCollabDoc}
            />
          )}
          {isAsk && (
            <AskStep workspaceId={workspaceId} onAnswered={() => setAnswered(true)} />
          )}
          <StepControls
            onContinue={onContinue}
            onSkip={skip}
            continueLabel={continueLabel}
            canContinue={canContinue}
          />
        </div>
      </main>
    </div>
  );
}

function AboutStep({
  role,
  referralSource,
  useCase,
  onRole,
  onReferral,
  onUseCase,
}: {
  role: string;
  referralSource: string;
  useCase: string;
  onRole: (v: string) => void;
  onReferral: (v: string) => void;
  onUseCase: (v: string) => void;
}) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          First, tell us about you
        </h1>
        <p className="text-sm text-dim max-w-lg">
          Three quick questions so we can tailor Stash to how you&rsquo;ll use it.
        </p>
      </div>
      <Field label="What's your role?">
        <PillGroup options={ROLE_OPTIONS} value={role} onChange={onRole} />
      </Field>
      <Field label="How did you hear about us?">
        <PillGroup options={REFERRAL_OPTIONS} value={referralSource} onChange={onReferral} />
      </Field>
      <Field label="What do you want to use Stash for?" optional>
        <textarea
          value={useCase}
          onChange={(e) => onUseCase(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="e.g. give my coding agents a shared knowledge base across our repos"
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-[13.5px] text-foreground placeholder:text-muted/70 focus:border-brand focus:outline-none"
        />
      </Field>
    </div>
  );
}

function Field({
  label,
  optional,
  children,
}: {
  label: string;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <label className="text-[13px] font-medium text-foreground">
        {label}
        {optional && <span className="ml-1.5 text-[11px] font-normal text-muted">optional</span>}
      </label>
      {children}
    </div>
  );
}

function PillGroup({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const selected = value === option;
        return (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            className={`rounded-full border px-3 py-1.5 text-[12.5px] transition-colors ${
              selected
                ? "border-brand bg-brand text-white"
                : "border-border bg-surface text-dim hover:border-foreground/40 hover:text-foreground"
            }`}
          >
            {option}
          </button>
        );
      })}
    </div>
  );
}

function IntroStep() {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Welcome to Stash
        </h1>
        <p className="text-sm text-dim max-w-lg">
          Stash gives your agents one place to reach everything they need — in the
          format they&rsquo;re fluent in.
        </p>
      </div>
      <ul className="space-y-3">
        <IntroPoint title="Connect any data source">
          GitHub, Google Drive, Gmail, Notion, Slack, Granola, an Obsidian vault. Your
          agent navigates each like a file system and searches across all of them.
        </IntroPoint>
        <IntroPoint title="A workspace built for agents">
          Pages in HTML and markdown, files, and your agent session transcripts —
          stored the way agents read and write, not buried in a UI.
        </IntroPoint>
        <IntroPoint title="Share when you need to">
          Bundle anything into a Cartridge with a shareable link, or give specific
          people access to a folder — so teammates and their agents work from the
          same context.
        </IntroPoint>
      </ul>
      <div className="rounded-lg border border-border bg-surface px-4 py-3 text-[13px] text-muted">
        Two quick steps: <span className="text-foreground">connect a source</span>,
        then <span className="text-foreground">ask your agent a question</span> over
        it. You can skip and do this later anytime.
      </div>
    </div>
  );
}

function IntroPoint({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
      <div>
        <div className="text-[14px] font-medium text-foreground">{title}</div>
        <div className="text-[13px] text-dim">{children}</div>
      </div>
    </li>
  );
}

function ConnectStep({
  workspaceId,
  onSourceCountChange,
  onObsidianAdded,
  onCollabDoc,
}: {
  workspaceId: string | null;
  onSourceCountChange: (n: number) => void;
  onObsidianAdded: () => void;
  onCollabDoc: () => void;
}) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Connect a data source
        </h1>
        <p className="text-sm text-dim max-w-md">
          Connect a source and your agent can read it — navigate it like a file system
          and search across everything you connect.
        </p>
      </div>
      <SourceConnectorList
        workspaceId={workspaceId}
        returnTo="/onboarding?step=3"
        onSourceCountChange={onSourceCountChange}
        onObsidianUploaded={onObsidianAdded}
      />
      <button
        type="button"
        onClick={onCollabDoc}
        className="group flex w-full items-center justify-between gap-3 rounded-lg border border-dashed border-border bg-surface px-4 py-3 text-left transition-colors hover:border-brand"
      >
        <div>
          <div className="text-[13.5px] font-medium text-foreground">
            Just want a place to write with your agent?
          </div>
          <div className="text-[12px] text-muted">
            Skip connecting sources — start a collaborative doc instead.
          </div>
        </div>
        <span className="text-muted transition-colors group-hover:text-brand">&rarr;</span>
      </button>
    </div>
  );
}

function AskStep({
  workspaceId,
  onAnswered,
}: {
  workspaceId: string | null;
  onAnswered: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Ask your agent
        </h1>
        <p className="text-sm text-dim max-w-md">
          Ask it something about your knowledge base.
        </p>
      </div>
      <MemoryAskStep workspaceId={workspaceId} onAnswered={onAnswered} />
    </div>
  );
}

function ProgressBar({ stepIdx }: { stepIdx: number }) {
  const labels = ["About you", "Welcome", "Connect", "Ask"];
  return (
    <div className="flex items-center gap-2">
      {labels.map((label, i) => {
        const isCurrent = i === Math.min(stepIdx, labels.length - 1);
        const reached = i <= stepIdx;
        return (
          <span
            key={label}
            className={`flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.18em] ${
              isCurrent ? "text-foreground" : reached ? "text-muted" : "text-muted/50"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                isCurrent ? "bg-brand" : reached ? "bg-foreground/40" : "bg-border"
              }`}
            />
            {label}
          </span>
        );
      })}
    </div>
  );
}

function StepControls({
  onContinue,
  onSkip,
  continueLabel,
  canContinue,
}: {
  onContinue: () => void;
  onSkip: () => void;
  continueLabel: string;
  canContinue: boolean;
}) {
  return (
    <div className="flex items-center justify-between pt-2">
      <button
        type="button"
        onClick={onSkip}
        className="text-[12px] text-muted hover:text-foreground transition-colors"
      >
        Skip onboarding
      </button>
      <button
        type="button"
        onClick={onContinue}
        disabled={!canContinue}
        className="rounded-md bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {continueLabel}
      </button>
    </div>
  );
}
