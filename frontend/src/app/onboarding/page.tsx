"use client";

import { Suspense, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { addExternalStash, getToken, listMyWorkspaces } from "../../lib/api";

import FirstShareStep from "./steps/FirstShareStep";
import TemplatesStep from "./steps/TemplatesStep";
import ImportsStep from "./steps/ImportsStep";
import InviteStep from "./steps/InviteStep";
import DoneStep from "./steps/DoneStep";

// Read the token from localStorage in an SSR-safe way. useSyncExternalStore
// gives us the right value on first client render without setState-in-effect.
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

const STEPS = ["1", "2", "3", "4", "done"] as const;
type Step = (typeof STEPS)[number];

const STEP_LABELS: Record<Step, string> = {
  "1": "Share",
  "2": "Templates",
  "3": "Sources",
  "4": "Invite",
  done: "Done",
};

function parseStep(raw: string | null): Step {
  return STEPS.includes(raw as Step) ? (raw as Step) : "1";
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-muted">Loading…</div>}>
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

  const step = parseStep(searchParams.get("step"));

  useEffect(() => {
    if (!loading && apiKey === null) {
      router.replace("/login");
    }
  }, [loading, apiKey, router]);

  useEffect(() => {
    if (!apiKey) return;
    listMyWorkspaces()
      .then(({ workspaces }) => {
        if (workspaces.length > 0) setWorkspaceId(workspaces[0].id);
      })
      .catch(() => {});
  }, [apiKey]);

  function gotoStep(next: Step) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("step", next);
    router.push(`/onboarding?${params.toString()}`);
  }

  function nextStep() {
    const i = STEPS.indexOf(step);
    gotoStep(STEPS[Math.min(i + 1, STEPS.length - 1)]);
  }

  function skipToWorkspace() {
    if (workspaceId) router.push(`/workspaces/${workspaceId}`);
    else router.push("/");
  }

  if (loading || !apiKey) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 px-4 py-10">
        <div className="mx-auto w-full max-w-2xl space-y-8">
          <ProgressBar step={step} onJump={gotoStep} />
          <StepBody
            step={step}
            apiKey={apiKey}
            workspaceId={workspaceId}
            onContinue={nextStep}
            onSkip={step === "done" ? skipToWorkspace : nextStep}
            onSkipAll={skipToWorkspace}
          />
        </div>
      </main>
    </div>
  );
}

function ProgressBar({ step, onJump }: { step: Step; onJump: (s: Step) => void }) {
  const currentIndex = STEPS.indexOf(step);
  return (
    <div className="flex items-center gap-2">
      {STEPS.map((s, i) => {
        const reached = i <= currentIndex;
        const isCurrent = s === step;
        return (
          <button
            key={s}
            type="button"
            onClick={() => onJump(s)}
            disabled={i > currentIndex}
            className={`flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.18em] transition-colors ${
              isCurrent ? "text-foreground" : reached ? "text-muted hover:text-foreground" : "text-muted/50"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                isCurrent ? "bg-brand" : reached ? "bg-foreground/40" : "bg-border"
              }`}
            />
            {STEP_LABELS[s]}
          </button>
        );
      })}
    </div>
  );
}

function StepBody({
  step,
  apiKey,
  workspaceId,
  onContinue,
  onSkip,
  onSkipAll,
}: {
  step: Step;
  apiKey: string;
  workspaceId: string | null;
  onContinue: () => void;
  onSkip: () => void;
  onSkipAll: () => void;
}) {
  return (
    <div className="space-y-8">
      {step === "1" && <FirstShareStep apiKey={apiKey} />}
      {step === "2" && (
        <TemplatesStepContainer workspaceId={workspaceId} onContinue={onContinue} onSkip={onSkip} />
      )}
      {step === "3" && <ImportsStep workspaceId={workspaceId} />}
      {step === "4" && <InviteStep workspaceId={workspaceId} />}
      {step === "done" && <DoneStep workspaceId={workspaceId} />}

      {step !== "2" && step !== "done" && (
        <StepControls onContinue={onContinue} onSkip={onSkip} onSkipAll={onSkipAll} />
      )}
    </div>
  );
}

function StepControls({
  onContinue,
  onSkip,
  onSkipAll,
  continuing,
  continueLabel = "Continue",
}: {
  onContinue: () => void;
  onSkip: () => void;
  onSkipAll: () => void;
  continuing?: boolean;
  continueLabel?: string;
}) {
  return (
    <div className="flex items-center justify-between pt-2">
      <button
        type="button"
        onClick={onSkipAll}
        className="text-[12px] text-muted hover:text-foreground transition-colors"
      >
        Skip onboarding
      </button>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onSkip}
          className="text-[12px] text-muted hover:text-foreground transition-colors"
        >
          Skip this step
        </button>
        <button
          type="button"
          onClick={onContinue}
          disabled={continuing}
          className="rounded-md bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-hover disabled:opacity-60 transition-colors"
        >
          {continuing ? "…" : continueLabel}
        </button>
      </div>
    </div>
  );
}

// Templates step owns its own continue handler (it has to fork selected stashes
// before advancing), so we wrap it here with its own controls.
function TemplatesStepContainer({
  workspaceId,
  onContinue,
  onSkip,
}: {
  workspaceId: string | null;
  onContinue: () => void;
  onSkip: () => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(slug: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }

  const continueLabel = useMemo(() => {
    if (selected.size === 0) return "Continue";
    return `Add ${selected.size} and continue`;
  }, [selected.size]);

  async function handleContinue() {
    if (selected.size === 0 || !workspaceId) {
      onContinue();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      for (const slug of selected) {
        await addExternalStash(slug, workspaceId);
      }
      onContinue();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <>
      <TemplatesStep selected={selected} onToggle={toggle} busy={busy} error={error} />
      <StepControls
        onContinue={handleContinue}
        onSkip={onSkip}
        onSkipAll={onSkip}
        continuing={busy}
        continueLabel={continueLabel}
      />
    </>
  );
}
