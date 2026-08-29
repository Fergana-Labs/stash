"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import CopyableCommandBlock from "../../components/CopyableCommandBlock";
import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { track } from "../../lib/analytics";
import {
  getOnboardingPreferences,
  getOnboardingStatus,
  putOnboardingPreferences,
  updateMe,
  type OnboardingStatus,
} from "../../lib/api";

const REFRESH_MS = 3_000;
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

const DEFAULT_PREFERENCES = {
  enabled_agents: ["claude", "codex", "cursor", "opencode", "gemini", "openclaw", "hermes"],
  record_scope: "everything" as const,
  import_history: true,
  claude_md_opt_in: true,
};

export default function OnboardingPage() {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <OnboardingInner />
    </Suspense>
  );
}

function OnboardingInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading, logout } = useAuth();
  const isConnect = searchParams.get("step") === "connect";
  const [prepared, setPrepared] = useState(false);
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [error, setError] = useState("");
  const completionTracked = useRef(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (loading || !user) return;
    let cancelled = false;

    async function prepare() {
      try {
        const { preferences } = await getOnboardingPreferences();
        if (preferences === null) await putOnboardingPreferences(DEFAULT_PREFERENCES);
        if (cancelled) return;
        setPrepared(true);
        track("onboarding.viewed", {});
      } catch (reason) {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Could not prepare Stash setup");
      }
    }

    void prepare();
    return () => {
      cancelled = true;
    };
  }, [loading, user]);

  const refresh = useCallback(async () => {
    try {
      setStatus(await getOnboardingStatus());
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not check for imported sessions");
    }
  }, []);

  useEffect(() => {
    if (!prepared || !isConnect) return;
    track("onboarding.step_viewed", { step_name: "connect" });
    void refresh();
    const timer = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [prepared, isConnect, refresh]);

  useEffect(() => {
    if (!isConnect || status === null || status.curatable_trace_count === 0) return;
    if (!completionTracked.current) {
      completionTracked.current = true;
      track("onboarding.completed", { sessions: status.curatable_trace_count });
    }
    router.replace("/");
  }, [isConnect, status, router]);

  if (loading || !user || !prepared) return <LoadingScreen />;
  if (isConnect && status !== null && status.curatable_trace_count > 0) {
    return <LoadingScreen />;
  }

  return (
    <div className="flex min-h-screen flex-col bg-base">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 px-6 py-10">
        <div className="mx-auto w-full max-w-2xl">
          <StepIndicator connect={isConnect} />
          {isConnect ? (
            <ConnectStep
              error={error}
              onComplete={() => {
                track("onboarding.completed", { completion_method: "manual" });
                router.push("/");
              }}
            />
          ) : (
            <AboutStep
              onContinue={() => router.push("/onboarding?step=connect")}
              onSkip={() => {
                track("onboarding.skipped", { step_name: "about" });
                router.push("/");
              }}
            />
          )}
        </div>
      </main>
    </div>
  );
}

function AboutStep({ onContinue, onSkip }: { onContinue: () => void; onSkip: () => void }) {
  const [roles, setRoles] = useState<string[]>([]);
  const [roleOther, setRoleOther] = useState("");
  const [referral, setReferral] = useState("");
  const [referralOther, setReferralOther] = useState("");
  const [useCase, setUseCase] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const roleAnswer = useMemo(() => {
    if (roles.length === 0 || (roles.includes("Other") && !roleOther.trim())) return "";
    return roles
      .map((role) => (role === "Other" ? `Other: ${roleOther.trim()}` : role))
      .join(", ");
  }, [roles, roleOther]);
  const referralAnswer =
    referral === "Other" ? referralOther.trim() && `Other: ${referralOther.trim()}` : referral;
  const canContinue = Boolean(roleAnswer && referralAnswer && !submitting);

  async function submit() {
    if (!canContinue) return;
    setSubmitting(true);
    setError("");
    try {
      await updateMe({
        role: roleAnswer,
        referral_source: referralAnswer,
        use_case: useCase.trim() || undefined,
      });
      track("onboarding.about_submitted", {
        role: roleAnswer,
        referral_source: referralAnswer,
      });
      onContinue();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save your answers");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mt-8">
      <h1 className="font-display text-[28px] font-bold leading-tight tracking-tight text-foreground">
        First, tell us about you
      </h1>
      <p className="mt-2 max-w-lg text-[14px] text-muted-foreground">
        A few quick questions so we can tailor Stash to how you&apos;ll use it.
      </p>

      <div className="mt-7 space-y-6">
        <Field label="What's your role? Pick as many as fit.">
          <PillGroup
            options={ROLE_OPTIONS}
            selected={roles}
            onToggle={(role) =>
              setRoles((current) =>
                current.includes(role)
                  ? current.filter((candidate) => candidate !== role)
                  : [...current, role],
              )
            }
          />
          {roles.includes("Other") && (
            <OtherInput value={roleOther} onChange={setRoleOther} placeholder="What's your role?" />
          )}
        </Field>

        <Field label="How did you hear about us?">
          <PillGroup
            options={REFERRAL_OPTIONS}
            selected={referral ? [referral] : []}
            onToggle={(option) => setReferral(referral === option ? "" : option)}
          />
          {referral === "Other" && (
            <OtherInput
              value={referralOther}
              onChange={setReferralOther}
              placeholder="Where did you hear about us?"
            />
          )}
        </Field>

        <Field label="What do you want to use Stash for?" optional>
          <textarea
            value={useCase}
            onChange={(event) => setUseCase(event.target.value)}
            rows={3}
            maxLength={2000}
            placeholder="e.g. turn my coding-agent sessions into reusable Skills"
            className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[13.5px] text-foreground placeholder:text-muted-foreground/70 focus:border-brand focus:outline-none"
          />
        </Field>
      </div>

      {error && <p className="mt-4 text-[12.5px] text-error">{error}</p>}
      <div className="mt-8 flex items-center justify-between">
        <button
          type="button"
          onClick={onSkip}
          className="cursor-pointer text-[12px] text-muted-foreground hover:text-foreground"
        >
          Skip onboarding
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!canContinue}
          className="cursor-pointer rounded-md bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Saving…" : "Continue"}
        </button>
      </div>
    </div>
  );
}

function ConnectStep({ error, onComplete }: { error: string; onComplete: () => void }) {
  return (
    <div className="mt-8">
      <h1 className="font-display text-[30px] font-bold tracking-tight text-foreground">
        Turn your traces into Skills
      </h1>
      <p className="mt-2 max-w-2xl text-[14px] leading-6 text-muted-foreground">
        Connect Stash once. It imports your five most recent coding sessions, then creates your
        first three Skills automatically.
      </p>
      {error && <p className="mt-4 text-[12.5px] text-error">{error}</p>}
      <div className="mt-8 divide-y divide-border border-y border-border">
        <ProductStep number={1} title="Connect Stash">
          <p className="text-[13px] leading-5 text-muted-foreground">
            Run this once in your terminal. Stash finds your coding agents and privately imports
            only your five most recent sessions to get started. Common API keys and access tokens
            are automatically redacted before upload.
          </p>
          <div className="mt-4 max-w-xl">
            <CopyableCommandBlock commands={CLI_INSTALL_COMMAND} />
          </div>
        </ProductStep>
        <ProductStep number={2} title="Stash automatically improves your agent">
          <p className="text-[13px] leading-5 text-muted-foreground">
            Stash finds reusable patterns in your sessions, turns them into Skills, and keeps them
            available to your coding agents.
          </p>
        </ProductStep>
        <ProductStep number={3} title="Share with your team">
          <p className="text-[13px] leading-5 text-muted-foreground">
            Share the Skills that work so everyone&apos;s agents benefit from what your team learns.
          </p>
        </ProductStep>
      </div>
      <div className="mt-6 flex justify-end">
        <button
          type="button"
          onClick={onComplete}
          className="cursor-pointer rounded-md bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-hover"
        >
          Complete onboarding
        </button>
      </div>
    </div>
  );
}

function ProductStep({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-4 py-6 sm:grid-cols-[32px_1fr]">
      <span className="flex h-6 w-6 items-center justify-center rounded-full border border-border text-[11px] font-medium text-muted-foreground">
        {number}
      </span>
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold text-foreground">{title}</h2>
        <div className="mt-2">{children}</div>
      </div>
    </section>
  );
}

function StepIndicator({ connect }: { connect: boolean }) {
  return (
    <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
      <span className={connect ? "text-muted-foreground" : "font-medium text-foreground"}>
        {connect ? "✓" : "●"} About you
      </span>
      <span className={connect ? "font-medium text-foreground" : "text-muted-foreground/50"}>
        {connect ? "●" : "○"} Connect Stash
      </span>
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
      <div className="text-[13px] font-medium text-foreground">
        {label}
        {optional && (
          <span className="ml-1.5 text-[11px] font-normal text-muted-foreground">optional</span>
        )}
      </div>
      {children}
    </div>
  );
}

function PillGroup({
  options,
  selected,
  onToggle,
}: {
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const active = selected.includes(option);
        return (
          <button
            key={option}
            type="button"
            aria-pressed={active}
            onClick={() => onToggle(option)}
            className={`cursor-pointer rounded-full border px-3 py-1.5 text-[12.5px] transition-colors ${
              active
                ? "border-brand bg-brand text-white"
                : "border-border bg-surface text-muted-foreground hover:text-foreground"
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
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      maxLength={200}
      autoFocus
      placeholder={placeholder}
      className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[13.5px] text-foreground placeholder:text-muted-foreground/70 focus:border-brand focus:outline-none"
    />
  );
}

function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center text-muted-foreground">
      Loading…
    </div>
  );
}
