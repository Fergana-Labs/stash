"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { track } from "../../lib/analytics";
import { updateMe } from "../../lib/api";

// The whole flow: a few questions about the user, then one instruction —
// connect your agent. Everything else Stash does grows out of the
// transcripts that starts, so onboarding refuses to offer detours.
const STEP_NAMES = ["about", "connect"] as const;

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
  // Roles are multi-answer: plenty of people are a founder *and* an engineer.
  const [roles, setRoles] = useState<string[]>([]);
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

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted-foreground">Loading…</div>
    );
  }

  // 0 = about, 1 = connect your agent.
  const isAbout = stepIdx <= 0;

  const continueLabel = isAbout ? "Continue" : "Finish";
  // "Other" only counts once it's spelled out, so picking it without typing
  // leaves the question unanswered rather than sending a bare "Other".
  const otherSpelledOut = !roles.includes("Other") || Boolean(roleOther.trim());
  const roleAnswer =
    roles.length > 0 && otherSpelledOut
      ? roles.map((r) => (r === "Other" ? `Other: ${roleOther.trim()}` : r)).join(", ")
      : "";
  const referralAnswer =
    referralSource === "Other"
      ? referralOther.trim() && `Other: ${referralOther.trim()}`
      : referralSource;
  // About: role + referral are required, and "Other" needs to be spelled out
  // (use-case is optional).
  const canContinue = isAbout ? Boolean(roleAnswer && referralAnswer) : true;
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
    finishAndExit();
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 px-4 py-10">
        <div className="mx-auto w-full max-w-2xl space-y-8">
          <ProgressBar stepIdx={stepIdx} />
          {isAbout && (
            <AboutStep
              roles={roles}
              roleOther={roleOther}
              referralSource={referralSource}
              referralOther={referralOther}
              useCase={useCase}
              onToggleRole={(r) =>
                setRoles((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]))
              }
              onRoleOther={setRoleOther}
              onReferral={setReferralSource}
              onReferralOther={setReferralOther}
              onUseCase={setUseCase}
            />
          )}
          {!isAbout && <ConnectAgentStep />}
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
  roles,
  roleOther,
  referralSource,
  referralOther,
  useCase,
  onToggleRole,
  onRoleOther,
  onReferral,
  onReferralOther,
  onUseCase,
}: {
  roles: string[];
  roleOther: string;
  referralSource: string;
  referralOther: string;
  useCase: string;
  onToggleRole: (v: string) => void;
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
      <Field label="What's your role? Pick as many as fit.">
        <PillGroup options={ROLE_OPTIONS} selected={roles} onToggle={onToggleRole} />
        {roles.includes("Other") && (
          <OtherInput value={roleOther} onChange={onRoleOther} placeholder="What's your role?" />
        )}
      </Field>
      <Field label="How did you hear about us?">
        <PillGroup
          options={REFERRAL_OPTIONS}
          selected={referralSource ? [referralSource] : []}
          onToggle={(v) => onReferral(referralSource === v ? "" : v)}
        />
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

/** Pills for one question. `selected` carries every chosen answer, so the same
 *  component serves the multi-answer role question and the single-answer
 *  referral one — the caller's onToggle decides which. */
function PillGroup({
  options,
  selected,
  onToggle,
}: {
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const isSelected = selected.includes(option);
        return (
          <button
            key={option}
            type="button"
            aria-pressed={isSelected}
            onClick={() => onToggle(option)}
            className={`cursor-pointer rounded-full border px-3 py-1.5 text-[12.5px] transition-colors ${
              isSelected
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

// What the installer actually does, in order — mirrors install.sh and the
// `stash signin` setup wizard. Claim nothing the code doesn't do.
const INSTALLER_STEPS = [
  "Installs the stash CLI (a small command-line tool; safe to re-run).",
  "Opens your browser to sign you in — the terminal never sees your password.",
  "Asks which folders to record agent sessions from: everywhere, or only ones you pick.",
  "Asks which coding agents (Claude Code, Codex, Cursor, …) should record — only checked agents upload anything.",
  "Uploads those agents' session transcripts to your Stash. They're private to you unless you share them, and you can pause recording anytime with stash stop.",
];

/** The whole second step: one instruction. The installer signs you in and
 *  runs the setup wizard, so this screen never needs a second command. */
function ConnectAgentStep() {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Now connect your agent
        </h1>
        <p className="text-sm text-dim max-w-lg">
          Run this in your terminal — the installer signs you in and sets up session
          recording.
        </p>
      </div>
      <CommandBlock command={CLI_INSTALL_COMMAND} />
      <div className="space-y-2">
        <p className="text-[13px] font-medium text-foreground">What this does</p>
        <ul className="max-w-lg space-y-1.5">
          {INSTALLER_STEPS.map((step) => (
            <li key={step} className="flex gap-2 text-[13px] leading-5 text-dim">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-brand" />
              {step}
            </li>
          ))}
        </ul>
        <p className="text-[12.5px] text-muted-foreground max-w-lg">
          It also offers — and asks first — to import your past agent conversations and
          to add Stash usage instructions to your repo&rsquo;s CLAUDE.md.
        </p>
      </div>
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

function ProgressBar({ stepIdx }: { stepIdx: number }) {
  const labels = ["About you", "Connect your agent"];
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
