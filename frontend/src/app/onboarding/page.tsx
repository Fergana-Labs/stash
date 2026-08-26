"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { track } from "../../lib/analytics";
import {
  getClaudeMdBlock,
  getOnboardingPreferences,
  putOnboardingPreferences,
  updateMe,
  type OnboardingPreferences,
} from "../../lib/api";

// The whole flow: a few questions about the user, the setup choices the CLI
// will apply, then one instruction — connect your agent. Everything else
// Stash does grows out of the transcripts that starts, so onboarding refuses
// to offer detours.
const STEP_NAMES = ["about", "setup", "connect"] as const;

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

// Mirrors _SUPPORTED_AGENTS / _AGENT_LABEL in cli/main.py — the CLI is what
// applies this choice, so only agents it can record are offered here.
const AGENT_OPTIONS = [
  { id: "claude", label: "Claude Code" },
  { id: "codex", label: "Codex" },
  { id: "cursor", label: "Cursor" },
  { id: "opencode", label: "opencode" },
  { id: "gemini", label: "Gemini CLI" },
  { id: "openclaw", label: "Openclaw" },
  { id: "hermes", label: "Hermes" },
] as const;

const DEFAULT_PREFERENCES: OnboardingPreferences = {
  enabled_agents: AGENT_OPTIONS.map((a) => a.id),
  record_scope: "everything",
  import_history: true,
  claude_md_opt_in: true,
};

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
  const [prefs, setPrefs] = useState<OnboardingPreferences>(DEFAULT_PREFERENCES);
  // True once the choices are known to be stored server-side — the connect
  // step may only claim "the command asks nothing" when that's actually true.
  const [prefsStored, setPrefsStored] = useState(false);
  const [prefsError, setPrefsError] = useState("");

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

  // Prefill from choices stored earlier (e.g. a reload mid-flow). Display
  // convenience only — the PUT on Continue is the write that must not fail
  // silently.
  useEffect(() => {
    if (loading || !user) return;
    getOnboardingPreferences()
      .then(({ preferences }) => {
        if (!preferences) return;
        setPrefs({
          enabled_agents: preferences.enabled_agents,
          record_scope: preferences.record_scope,
          import_history: preferences.import_history,
          claude_md_opt_in: preferences.claude_md_opt_in,
        });
        setPrefsStored(true);
      })
      .catch(() => {});
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

  // 0 = about, 1 = setup choices, 2 = connect your agent.
  const isAbout = stepIdx <= 0;
  const isSetup = stepIdx === 1;

  const continueLabel = stepIdx >= STEP_NAMES.length - 1 ? "Finish" : "Continue";
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
    if (isSetup) {
      // The CLI reads these at signin — a failed save must stop the flow, or
      // the connect step would promise choices the server never received.
      setPrefsError("");
      try {
        await putOnboardingPreferences(prefs);
      } catch (e) {
        setPrefsError(e instanceof Error ? e.message : "Could not save your choices");
        return;
      }
      setPrefsStored(true);
      track("onboarding.setup_submitted", {
        enabled_agents: prefs.enabled_agents.join(","),
        record_scope: prefs.record_scope,
        import_history: prefs.import_history,
        claude_md_opt_in: prefs.claude_md_opt_in,
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
          {isSetup && <SetupStep prefs={prefs} onChange={setPrefs} error={prefsError} />}
          {!isAbout && !isSetup && <ConnectAgentStep prefs={prefs} prefsStored={prefsStored} />}
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

/** The setup choices the CLI applies at signin. Everything here maps 1:1 to
 *  what `stash signin` actually does with the stored preferences — no
 *  speculative settings. */
function SetupStep({
  prefs,
  onChange,
  error,
}: {
  prefs: OnboardingPreferences;
  onChange: (p: OnboardingPreferences) => void;
  error: string;
}) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Set up session recording
        </h1>
        <p className="text-sm text-dim max-w-lg">
          Answer here instead of in the terminal — the install command on the next step
          applies these choices without asking questions. Sessions are private to you
          unless you share them, and <code className="font-mono text-[12px]">stash stop</code>{" "}
          pauses recording anytime.
        </p>
      </div>
      <Field label="Which coding agents should Stash record?">
        <PillGroup
          options={AGENT_OPTIONS.map((a) => a.label)}
          selected={AGENT_OPTIONS.filter((a) => prefs.enabled_agents.includes(a.id)).map(
            (a) => a.label,
          )}
          onToggle={(label) => {
            const agent = AGENT_OPTIONS.find((a) => a.label === label);
            if (!agent) return;
            const on = prefs.enabled_agents.includes(agent.id);
            onChange({
              ...prefs,
              enabled_agents: on
                ? prefs.enabled_agents.filter((id) => id !== agent.id)
                : [...prefs.enabled_agents, agent.id],
            });
          }}
        />
        <p className="text-[12px] text-muted-foreground max-w-lg">
          Only checked agents upload anything. Agents you don&rsquo;t have installed are
          skipped on your machine.
        </p>
      </Field>
      <Field label="Where should sessions be recorded?">
        <div className="space-y-1.5">
          <RadioRow
            checked={prefs.record_scope === "everything"}
            title="Everywhere on this machine"
            detail="Every folder your agents run in."
            onSelect={() => onChange({ ...prefs, record_scope: "everything" })}
          />
          <RadioRow
            checked={prefs.record_scope === "selected_folders"}
            title="Only a folder I pick"
            detail="A browser can't see your folders — the install command asks this one question in the terminal."
            onSelect={() => onChange({ ...prefs, record_scope: "selected_folders" })}
          />
        </div>
      </Field>
      <CheckboxRow
        checked={prefs.import_history}
        title="Import my past agent conversations"
        detail="Runs in the background after install; progress shows on your Home page."
        onToggle={() => onChange({ ...prefs, import_history: !prefs.import_history })}
      />
      <div className="space-y-2">
        <CheckboxRow
          checked={prefs.claude_md_opt_in}
          title="Add Stash instructions to my repo's CLAUDE.md"
          detail="So agents working there know how to use Stash."
          onToggle={() => onChange({ ...prefs, claude_md_opt_in: !prefs.claude_md_opt_in })}
        />
        <ClaudeMdPreview />
      </div>
      {error && <p className="text-[12.5px] text-red-500">{error}</p>}
    </div>
  );
}

function RadioRow({
  checked,
  title,
  detail,
  onSelect,
}: {
  checked: boolean;
  title: string;
  detail: string;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      onClick={onSelect}
      className={`flex w-full max-w-lg cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors ${
        checked ? "border-brand bg-brand/5" : "border-border bg-surface hover:border-foreground/40"
      }`}
    >
      <span
        className={`mt-[3px] flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border ${
          checked ? "border-brand" : "border-border"
        }`}
      >
        {checked && <span className="h-2 w-2 rounded-full bg-brand" />}
      </span>
      <span>
        <span className="block text-[13px] font-medium text-foreground">{title}</span>
        <span className="block text-[12px] text-muted-foreground">{detail}</span>
      </span>
    </button>
  );
}

function CheckboxRow({
  checked,
  title,
  detail,
  onToggle,
}: {
  checked: boolean;
  title: string;
  detail: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      onClick={onToggle}
      className="flex w-full max-w-lg cursor-pointer items-start gap-2.5 rounded-lg border border-border bg-surface px-3 py-2 text-left transition-colors hover:border-foreground/40"
    >
      <span
        className={`mt-[3px] flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[4px] border text-[10px] text-white ${
          checked ? "border-brand bg-brand" : "border-border"
        }`}
      >
        {checked && "✓"}
      </span>
      <span>
        <span className="block text-[13px] font-medium text-foreground">{title}</span>
        <span className="block text-[12px] text-muted-foreground">{detail}</span>
      </span>
    </button>
  );
}

/** Appending to someone's CLAUDE.md is a write into their repo — show the
 *  exact block on request. The text comes from the backend, which serves the
 *  same file the CLI appends, so this preview can't drift from reality. */
function ClaudeMdPreview() {
  const [open, setOpen] = useState(false);
  const [block, setBlock] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open || block) return;
    getClaudeMdBlock()
      .then(({ block }) => setBlock(block))
      .catch(() => setFailed(true));
  }, [open, block]);

  return (
    <div className="max-w-lg space-y-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="cursor-pointer text-[12px] text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
      >
        {open ? "Hide what gets appended" : "Show exactly what gets appended"}
      </button>
      {open && failed && (
        <p className="text-[12px] text-red-500">Couldn&rsquo;t load the preview.</p>
      )}
      {open && !failed && (
        <pre className="max-h-64 overflow-auto rounded-md border border-border bg-surface p-3 font-mono text-[11px] leading-4 text-dim whitespace-pre-wrap">
          {block || "Loading…"}
        </pre>
      )}
    </div>
  );
}

// What the install command actually does with stored choices, in order —
// mirrors install.sh and `_apply_web_onboarding` in cli/main.py. Claim
// nothing the code doesn't do.
function installerSteps(prefs: OnboardingPreferences, prefsStored: boolean): string[] {
  const steps = [
    "Installs the stash CLI (a small command-line tool; safe to re-run).",
    "Opens your browser to sign you in — the terminal never sees your password.",
  ];
  if (!prefsStored) {
    // Reached without saved choices (e.g. a direct link): the CLI falls back
    // to nothing — it simply still asks its questions in the terminal.
    steps.push(
      "Asks its setup questions in the terminal: which folders and agents to record, history import, CLAUDE.md.",
    );
    return steps;
  }
  steps.push(
    prefs.record_scope === "selected_folders"
      ? "Asks the one question a browser can't answer — which folder to record — then applies your other choices from here, printing each one. No other questions."
      : "Applies the choices you made here, printing each one. No questions.",
  );
  if (prefs.import_history) {
    steps.push(
      "Starts importing your past agent conversations in the background — progress shows on your Home page.",
    );
  }
  if (prefs.claude_md_opt_in) {
    steps.push("Appends the Stash block you previewed to your repo's CLAUDE.md.");
  }
  steps.push(
    "Recorded sessions are private to you unless you share them; pause anytime with stash stop.",
  );
  return steps;
}

/** The whole last step: one instruction. The installer signs you in and
 *  applies the choices from the previous step, so this screen never needs a
 *  second command. */
function ConnectAgentStep({
  prefs,
  prefsStored,
}: {
  prefs: OnboardingPreferences;
  prefsStored: boolean;
}) {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Now connect your agent
        </h1>
        <p className="text-sm text-dim max-w-lg">
          {prefsStored
            ? "Run this in your terminal. You already made the setup choices here, so it won't quiz you."
            : "Run this in your terminal — the installer signs you in and sets up session recording."}
        </p>
      </div>
      <CommandBlock command={CLI_INSTALL_COMMAND} />
      <div className="space-y-2">
        <p className="text-[13px] font-medium text-foreground">What this does</p>
        <ul className="max-w-lg space-y-1.5">
          {installerSteps(prefs, prefsStored).map((step) => (
            <li key={step} className="flex gap-2 text-[13px] leading-5 text-dim">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-brand" />
              {step}
            </li>
          ))}
        </ul>
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
  const labels = ["About you", "Set up recording", "Connect your agent"];
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
