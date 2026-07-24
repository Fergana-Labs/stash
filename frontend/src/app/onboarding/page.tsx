"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { track } from "../../lib/analytics";
import {
  createMyKey,
  createPage,
  getAgentApiKey,
  updateMe,
  updatePage,
  type ApiKeyCreated,
} from "../../lib/api";
import { generateCollabIntroMarkdown } from "../../lib/onboarding/collabIntro";
import { routes } from "../../lib/workspace-routes";
import SourceConnectorList from "../../components/integrations/SourceConnectorList";

import MemoryAskStep from "./paths/memory/MemoryAskStep";

// The linear flow: a few questions about the user, explain Stash, then try
// one of five entry points. The ask step only exists off the Connect path —
// asking the agent needs a connected source to ask about.
const STEP_NAMES = ["about", "intro", "try", "ask"] as const;

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
        <div className="min-h-screen flex items-center justify-center text-muted-foreground">Loading…</div>
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

  const exitToHome = useCallback(() => {
    router.push("/");
  }, [router]);

  const finishAndExit = useCallback(() => {
    track("onboarding.completed", { total_steps: STEP_NAMES.length });
    exitToHome();
  }, [exitToHome]);

  const skip = useCallback(() => {
    track("onboarding.skipped", { step_idx: stepIdx });
    exitToHome();
  }, [exitToHome, stepIdx]);

  // The "I just want to write with my agent" path: skip connecting sources,
  // seed a starter page, and drop the user straight into the collaborative
  // editor. This is the Google-Docs-for-agents wedge, so it bypasses the ask step.
  const finishToCollabDoc = useCallback(async () => {
    track("onboarding.collab_path_chosen", {});
    // The starter page embeds its own id in a copy-paste agent prompt, so we
    // create it empty and fill it in after. Self-hosted browsers hold a key
    // to embed; under managed Auth0 the prompt says `stash signin` instead.
    const apiKey = getAgentApiKey();
    const page = await createPage("Welcome to your Drive");
    const content = generateCollabIntroMarkdown({
      displayName: user?.display_name || user?.name || "",
      pageId: page.id,
      apiKey,
    });
    await updatePage(page.id, { content });
    router.push(`/p/${page.id}`);
  }, [user, router]);

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted-foreground">Loading…</div>
    );
  }

  // 0 = about, 1 = intro, 2 = try it out, 3 = ask.
  const isAbout = stepIdx <= 0;
  const isIntro = stepIdx === 1;
  const isTryItOut = stepIdx === 2;
  const isAsk = stepIdx >= 3;

  const continueLabel = isIntro
    ? "Get started"
    : isTryItOut
      ? "Finish"
      : isAsk
        ? "Launch"
        : "Continue";
  const roleAnswer = role === "Other" ? roleOther.trim() && `Other: ${roleOther.trim()}` : role;
  const referralAnswer =
    referralSource === "Other"
      ? referralOther.trim() && `Other: ${referralOther.trim()}`
      : referralSource;
  // About: role + referral are required, and "Other" needs to be spelled out
  // (use-case is optional). Try it out: Finish ends onboarding from any option;
  // the Connect option additionally offers the ask step once a source is
  // connected. Ask: only let them launch once the agent has actually replied.
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
      track("onboarding.about_submitted", {
        role: roleAnswer,
        referral_source: referralAnswer,
      });
      return goToStep(stepIdx + 1);
    }
    if (isTryItOut || isAsk) return void finishAndExit();
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
          {isTryItOut && (
            <TryItOutStep
              onCollabDoc={finishToCollabDoc}
              onAsk={() => goToStep(stepIdx + 1)}
            />
          )}
          {isAsk && <AskStep onAnswered={() => setAnswered(true)} />}
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
          A few quick questions so we can tailor Stash to how you&rsquo;ll use it.
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
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-[13.5px] text-foreground placeholder:text-muted-foreground/70 focus:border-brand focus:outline-none"
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
        {optional && <span className="ml-1.5 text-[11px] font-normal text-muted-foreground">optional</span>}
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
            aria-pressed={selected}
            onClick={() => onChange(selected ? "" : option)}
            className={`cursor-pointer rounded-full border px-3 py-1.5 text-[12.5px] transition-colors ${
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
      className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-[13.5px] text-foreground placeholder:text-muted-foreground/70 focus:border-brand focus:outline-none"
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
        <IntroPoint title="A curated context graph">
          While you sleep, curator agents dream over everything you saved and
          distill it into a living memory wiki every agent you run can read.
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

function TryItOutStep({
  onCollabDoc,
  onAsk,
}: {
  onCollabDoc: () => void;
  onAsk: () => void;
}) {
  const [sourceConnected, setSourceConnected] = useState(false);
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Try it out
        </h1>
        <p className="text-sm text-dim max-w-md">
          Five ways to start — open whichever fits.
        </p>
      </div>
      <TryOption
        badge="Build"
        lead="Use Stash as the memory store for your agent, over a plain API."
      >
        <BuildOption />
      </TryOption>
      <TryOption badge="Create" lead="A place to write with your agent — two cursors, one doc.">
        <button
          type="button"
          onClick={onCollabDoc}
          className="group flex w-full cursor-pointer items-center justify-between gap-3 rounded-lg border border-dashed border-border bg-surface px-4 py-3 text-left transition-colors hover:border-brand"
        >
          <div>
            <div className="text-[13.5px] font-medium text-foreground">
              Start a collaborative doc
            </div>
            <div className="text-[12px] text-muted-foreground">
              You and your agent edit the same page — two cursors at once.
            </div>
          </div>
          <span className="text-muted-foreground transition-colors group-hover:text-brand">&rarr;</span>
        </button>
      </TryOption>
      <TryOption
        badge="Connect"
        lead="Connect a data source your agent can navigate like a file system."
      >
        <div className="space-y-3">
          <SourceConnectorList
            returnTo="/onboarding?step=3"
            onConnectedChange={setSourceConnected}
          />
          {sourceConnected && (
            <div className="flex items-center justify-end">
              <button
                type="button"
                onClick={onAsk}
                className="cursor-pointer rounded-md bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-hover transition-colors"
              >
                Ask your agent about it &rarr;
              </button>
            </div>
          )}
        </div>
      </TryOption>
      <TryOption
        badge="Capture"
        lead="Stream every Claude Code / Codex session into Stash automatically."
      >
        <div className="space-y-2">
          <p className="text-[12px] text-dim">Run this in your terminal:</p>
          <CommandBlock command={CLI_INSTALL_COMMAND} />
          <CommandBlock command="stash signin" />
        </div>
      </TryOption>
      <TryOption badge="Clip" lead="Save anything you read, straight from your browser.">
        <a
          href={routes.extension}
          target="_blank"
          rel="noopener"
          className="group flex w-full cursor-pointer items-center justify-between gap-3 rounded-lg border border-dashed border-border bg-surface px-4 py-3 text-left transition-colors hover:border-brand"
        >
          <div>
            <div className="text-[13.5px] font-medium text-foreground">
              Get the browser extension
            </div>
            <div className="text-[12px] text-muted-foreground">
              Clip pages, import bookmarks, sync Instagram saves and ChatGPT/Claude chats.
            </div>
          </div>
          <span className="text-muted-foreground transition-colors group-hover:text-brand">&rarr;</span>
        </a>
      </TryOption>
    </div>
  );
}

// Each way to start is a collapsed accordion: badge + one-line description
// up front, the actual steps revealed on open.
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
    <details className="group rounded-lg border border-border bg-surface">
      <summary className="flex cursor-pointer list-none items-center gap-2.5 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <span className="rounded bg-brand/10 px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.1em] text-brand">
          {badge}
        </span>
        <span className="flex-1 text-[13px] text-dim">{lead}</span>
        <span className="text-muted-foreground transition-transform group-open:rotate-90">
          &rsaquo;
        </span>
      </summary>
      <div className="border-t border-border px-4 py-3">{children}</div>
    </details>
  );
}

function BuildOption() {
  const [minted, setMinted] = useState<ApiKeyCreated | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  async function handleCreate() {
    setCreating(true);
    setError("");
    try {
      setMinted(await createMyKey("onboarding", "full"));
      track("onboarding.api_key_minted", {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create key");
    } finally {
      setCreating(false);
    }
  }

  if (!minted) {
    return (
      <div className="space-y-2">
        <button
          type="button"
          onClick={handleCreate}
          disabled={creating}
          className="cursor-pointer rounded-md bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-hover disabled:opacity-60 transition-colors"
        >
          {creating ? "Creating…" : "Create API key"}
        </button>
        {error && <p className="text-[12px] text-error">{error}</p>}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-[12px] text-dim">
        Copy it now — this is the only time the full key will be shown. Manage keys in
        Settings.
      </p>
      <CommandBlock command={minted.api_key} />
      <p className="text-[12px] text-dim">Write your agent&rsquo;s first memory:</p>
      <CommandBlock
        command={`curl -X POST https://api.joinstash.ai/api/v1/me/sessions/events \\
  -H "Authorization: Bearer ${minted.api_key}" -H "Content-Type: application/json" \\
  -d '{"agent_name":"my-agent","session_id":"run-1","event_type":"learning","content":"hello memory"}'`}
      />
    </div>
  );
}

function CommandBlock({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-stretch gap-1.5">
      <pre className="min-w-0 flex-1 overflow-x-auto rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[11.5px] text-foreground">
        {command}
      </pre>
      <button
        type="button"
        onClick={async () => {
          await navigator.clipboard.writeText(command);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        className="shrink-0 cursor-pointer rounded-md border border-border bg-surface px-2.5 text-[11px] text-muted-foreground transition-colors hover:border-brand hover:text-foreground"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function AskStep({ onAnswered }: { onAnswered: () => void }) {
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
      <MemoryAskStep onAnswered={onAnswered} />
    </div>
  );
}

// "Ask" is deliberately absent — that step only exists off the Connect path,
// so it doesn't belong in the always-visible progress trail.
function ProgressBar({ stepIdx }: { stepIdx: number }) {
  const labels = ["About you", "Welcome", "Try it out"];
  return (
    <div className="flex items-center gap-2">
      {labels.map((label, i) => {
        const isCurrent = i === Math.min(stepIdx, labels.length - 1);
        const reached = i <= stepIdx;
        return (
          <span
            key={label}
            className={`flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.18em] ${
              isCurrent ? "text-foreground" : reached ? "text-muted-foreground" : "text-muted-foreground/50"
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
        className="cursor-pointer text-[12px] text-muted-foreground hover:text-foreground transition-colors"
      >
        Skip onboarding
      </button>
      <button
        type="button"
        onClick={onContinue}
        disabled={!canContinue}
        className="cursor-pointer rounded-md bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {continueLabel}
      </button>
    </div>
  );
}
