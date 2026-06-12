"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { track } from "../../lib/analytics";
import {
  createPage,
  getAgentApiKey,
  listMyKeys,
  listMyWorkspaces,
  updateMe,
  updatePage,
  type ApiKeyInfo,
} from "../../lib/api";
import { generateCollabIntroMarkdown } from "../../lib/onboarding/collabIntro";
import { seedWelcomePage } from "../../lib/onboarding/seedWelcome";
import SourceConnectorList from "../../components/integrations/SourceConnectorList";

import MemoryAskStep from "./paths/memory/MemoryAskStep";

// The linear flow: a few questions about the user, explain Stash, install the
// CLI, try an entry point, then ask the agent a real question, then launch.
const STEP_NAMES = ["about", "intro", "cli", "try", "ask"] as const;

const CLI_INSTALL_COMMAND = `bash -c "$(curl -fsSL https://joinstash.ai/install)"`;

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
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [sourceCount, setSourceCount] = useState(0);
  const [obsidianAdded, setObsidianAdded] = useState(false);
  const [answered, setAnswered] = useState(false);
  const [role, setRole] = useState("");
  const [roleOther, setRoleOther] = useState("");
  const [referralSource, setReferralSource] = useState("");
  const [referralOther, setReferralOther] = useState("");
  const [useCase, setUseCase] = useState("");

  const stepIdx = useMemo(() => {
    const raw = searchParams.get("step");
    const parsed = raw ? parseInt(raw, 10) : 1;
    return Number.isFinite(parsed) && parsed > 0 ? parsed - 1 : 0;
  }, [searchParams]);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    listMyWorkspaces()
      .then(({ workspaces }) => {
        const primary = workspaces.find((workspace) => workspace.is_primary) ?? workspaces[0];
        if (primary) setWorkspaceId(primary.id);
      })
      .catch(() => {});
  }, [user]);

  useEffect(() => {
    if (loading || !user) return;
    track("onboarding.viewed", { has_path: false });
  }, [loading, user]);

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
    // The starter page embeds its own id in a copy-paste agent prompt, so we
    // create it empty and fill it in after. Self-hosted browsers hold a key
    // to embed; under managed Auth0 the prompt says `stash login` instead.
    const apiKey = getAgentApiKey();
    const page = await createPage(workspaceId, "Welcome to your Drive");
    const content = generateCollabIntroMarkdown({
      displayName: user?.display_name || user?.name || "",
      pageId: page.id,
      apiKey,
    });
    await updatePage(workspaceId, page.id, { content });
    router.push(`/p/${page.id}`);
  }, [workspaceId, user, router]);

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">Loading…</div>
    );
  }

  // 0 = about, 1 = intro, 2 = cli, 3 = try it out, 4 = ask.
  const isAbout = stepIdx <= 0;
  const isIntro = stepIdx === 1;
  const isCli = stepIdx === 2;
  const isTryItOut = stepIdx === 3;
  const isAsk = stepIdx >= 4;

  const continueLabel = isIntro
    ? "Get started"
    : isAsk
      ? "Launch workspace"
      : "Continue";
  const roleAnswer = role === "Other" ? roleOther.trim() && `Other: ${roleOther.trim()}` : role;
  const referralAnswer =
    referralSource === "Other"
      ? referralOther.trim() && `Other: ${referralOther.trim()}`
      : referralSource;
  // About: role + referral are required, and "Other" needs to be spelled out
  // (use-case is optional). Try it out: Continue lives inside the Connect
  // option and is gated on a connected source. Ask: only let them launch once
  // the agent has actually replied.
  const canContinue = isAbout ? Boolean(roleAnswer && referralAnswer) : !isAsk || answered;
  const onContinue = async () => {
    if (isAbout) {
      try {
        await updateMe({
          role: roleAnswer,
          referral_source: referralAnswer,
          use_case: useCase || undefined,
        });
      } catch {
        // Best-effort — don't block onboarding on a profile write.
      }
      track("onboarding.about_submitted", { role: roleAnswer, referral_source: referralAnswer });
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
              roleOther={roleOther}
              referralSource={referralSource}
              referralOther={referralOther}
              useCase={useCase}
              onRole={setRole}
              onRoleOther={setRoleOther}
              onReferral={setReferralSource}
              onReferralOther={setReferralOther}
              onUseCase={setUseCase}
            />
          )}
          {isIntro && <IntroStep />}
          {isCli && <CliStep />}
          {isTryItOut && (
            <TryItOutStep
              workspaceId={workspaceId}
              onCollabDoc={finishToCollabDoc}
              onSourceCountChange={setSourceCount}
              onObsidianAdded={() => setObsidianAdded(true)}
              canContinue={sourceCount > 0 || obsidianAdded}
              onContinue={() => goToStep(stepIdx + 1)}
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
            hideContinue={isTryItOut}
          />
        </div>
      </main>
    </div>
  );
}

function AboutStep({
  role,
  roleOther,
  referralSource,
  referralOther,
  useCase,
  onRole,
  onRoleOther,
  onReferral,
  onReferralOther,
  onUseCase,
}: {
  role: string;
  roleOther: string;
  referralSource: string;
  referralOther: string;
  useCase: string;
  onRole: (v: string) => void;
  onRoleOther: (v: string) => void;
  onReferral: (v: string) => void;
  onReferralOther: (v: string) => void;
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
        {role === "Other" && (
          <OtherInput value={roleOther} onChange={onRoleOther} placeholder="What's your role?" />
        )}
      </Field>
      <Field label="How did you hear about us?">
        <PillGroup options={REFERRAL_OPTIONS} value={referralSource} onChange={onReferral} />
        {referralSource === "Other" && (
          <OtherInput
            value={referralOther}
            onChange={onReferralOther}
            placeholder="Where did you hear about us?"
          />
        )}
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

function OtherInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      maxLength={200}
      autoFocus
      placeholder={placeholder}
      className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-[13.5px] text-foreground placeholder:text-muted/70 focus:border-brand focus:outline-none"
    />
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
          GitHub, Drive, Gmail, Notion, Slack and more — one connection per source,
          and every agent you run can read all of them.
        </IntroPoint>
        <IntroPoint title="Capture every agent session">
          Transcripts stream in automatically — prompts, tool calls, artifacts — so
          your knowledge base accumulates with every run instead of evaporating when
          the session closes.
        </IntroPoint>
        <IntroPoint title="An agent-native Drive">
          HTML docs, Markdown, dashboards, decks — your agents&rsquo; work lands as
          real files. Edit visually, and share any folder or file as a link.
        </IntroPoint>
      </ul>
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

function CliStep() {
  const [cliKey, setCliKey] = useState<ApiKeyInfo | null>(null);

  // `stash login` mints an API key named "CLI (<device>)" the moment the user
  // approves the browser sign-in, so polling for one tells us the install
  // worked without the user having to confirm anything.
  useEffect(() => {
    if (cliKey) return;
    let firstCheck = true;
    let cancelled = false;
    const check = () => {
      const preexisting = firstCheck;
      firstCheck = false;
      listMyKeys()
        .then((keys) => {
          if (cancelled) return;
          const key = keys.find((k) => k.name.startsWith("CLI ("));
          if (!key) return;
          setCliKey(key);
          track("onboarding.cli_connected", { preexisting });
        })
        .catch(() => {});
    };
    check();
    const interval = setInterval(check, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [cliKey]);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Connect your coding agent
        </h1>
        <p className="text-sm text-dim max-w-lg">
          One command installs the Stash CLI and signs you in. This is how Stash
          compounds: your agents read this workspace, and everything they do flows
          back into it.
        </p>
      </div>
      <ul className="space-y-3">
        <IntroPoint title="Every session is captured">
          Prompts, tool calls, and artifacts from Claude Code, Codex, Cursor, and
          OpenCode stream in as they happen — nothing evaporates when a session
          closes.
        </IntroPoint>
        <IntroPoint title="Your agents can read everything">
          The CLI gives every agent you run access to your whole workspace —
          connected sources, files, and past sessions.
        </IntroPoint>
      </ul>
      <div className="space-y-2">
        <CommandBlock command={CLI_INSTALL_COMMAND} />
        <p className="text-[12px] text-muted">
          Already have the CLI? Run{" "}
          <code className="font-mono text-foreground/80">stash login</code> instead.
        </p>
      </div>
      <CliConnectedStatus cliKey={cliKey} />
    </div>
  );
}

function CliConnectedStatus({ cliKey }: { cliKey: ApiKeyInfo | null }) {
  if (cliKey) {
    return (
      <div className="flex items-center gap-2.5 rounded-lg border border-brand/40 bg-brand/5 px-3.5 py-2.5 text-[13px] text-foreground">
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
        Connected — <span className="font-medium">{cliKey.name}</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-border bg-surface px-3.5 py-2.5 text-[13px] text-dim">
      <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-muted" />
      Waiting for the CLI to connect — this updates by itself once you run the
      command.
    </div>
  );
}

function TryItOutStep({
  workspaceId,
  onCollabDoc,
  onSourceCountChange,
  onObsidianAdded,
  canContinue,
  onContinue,
}: {
  workspaceId: string | null;
  onCollabDoc: () => void;
  onSourceCountChange: (n: number) => void;
  onObsidianAdded: () => void;
  canContinue: boolean;
  onContinue: () => void;
}) {
  return (
    <div className="space-y-7">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Try it out
        </h1>
        <p className="text-sm text-dim max-w-md">
          Two ways to start — pick whichever fits.
        </p>
      </div>
      <TryOption
        badge="Create"
        lead="Just want a place to write with your agent?"
      >
        <button
          type="button"
          onClick={onCollabDoc}
          className="group flex w-full items-center justify-between gap-3 rounded-lg border border-dashed border-border bg-surface px-4 py-3 text-left transition-colors hover:border-brand"
        >
          <div>
            <div className="text-[13.5px] font-medium text-foreground">
              Start a collaborative doc
            </div>
            <div className="text-[12px] text-muted">
              You and your agent edit the same page — two cursors at once.
            </div>
          </div>
          <span className="text-muted transition-colors group-hover:text-brand">&rarr;</span>
        </button>
      </TryOption>
      <TryOption
        badge="Connect"
        lead="Connect a data source and your agent can navigate it like a file system."
      >
        <div className="space-y-3">
          <SourceConnectorList
            workspaceId={workspaceId}
            returnTo="/onboarding?step=4"
            onSourceCountChange={onSourceCountChange}
            onObsidianUploaded={onObsidianAdded}
          />
          <div className="flex items-center justify-end gap-3">
            {!canContinue && (
              <span className="text-[12px] text-muted">Connect a source to continue</span>
            )}
            <button
              type="button"
              onClick={onContinue}
              disabled={!canContinue}
              className="rounded-md bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Continue
            </button>
          </div>
        </div>
      </TryOption>
    </div>
  );
}

function TryOption({
  badge,
  lead,
  children,
}: {
  badge: string;
  lead: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2.5">
        <span className="rounded bg-brand/10 px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.1em] text-brand">
          {badge}
        </span>
        <span className="text-[13px] text-dim">{lead}</span>
      </div>
      {children}
    </div>
  );
}

function CommandBlock({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(command).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-surface px-2.5 py-1.5">
      <pre className="flex-1 overflow-x-auto font-mono text-[11.5px] text-foreground">
        {command}
      </pre>
      <button
        type="button"
        onClick={copy}
        className="shrink-0 text-[11px] text-muted hover:text-foreground transition-colors"
      >
        {copied ? "Copied" : "Copy"}
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
  const labels = ["About you", "Welcome", "Install CLI", "Try it out", "Ask"];
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
  hideContinue,
}: {
  onContinue: () => void;
  onSkip: () => void;
  continueLabel: string;
  canContinue: boolean;
  hideContinue?: boolean;
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
      {!hideContinue && (
        <button
          type="button"
          onClick={onContinue}
          disabled={!canContinue}
          className="rounded-md bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {continueLabel}
        </button>
      )}
    </div>
  );
}
