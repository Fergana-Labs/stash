"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";

import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { getToken, listMyWorkspaces } from "../../lib/api";
import { seedWelcomePage } from "../../lib/onboarding/seedWelcome";

import IntentStep from "./IntentStep";
import {
  PATHS,
  type MigrantSource,
  type PathId,
  type StepCtx,
} from "../../lib/onboarding/paths";

const VALID_PATHS: PathId[] = ["migrant", "memory", "sharing"];
const VALID_SOURCES: MigrantSource[] = ["notion", "obsidian", "github", "drive"];

// Scoped per user so registering as a different account on the same
// computer doesn't inherit the previous user's locked path.
function pathStorageKey(userId: string): string {
  return `stash_onboarding_path:${userId}`;
}

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

function isPathId(v: string | null): v is PathId {
  return !!v && (VALID_PATHS as string[]).includes(v);
}

function isMigrantSource(v: string | null): v is MigrantSource {
  return !!v && (VALID_SOURCES as string[]).includes(v);
}

export default function OnboardingPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-muted">
          Loading…
        </div>
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
  const [sharedUrl, setSharedUrl] = useState<string | null>(null);
  const [canContinue, setCanContinue] = useState(true);

  const path = useMemo<PathId | null>(() => {
    const q = searchParams.get("path");
    if (isPathId(q)) return q;
    if (typeof window !== "undefined" && user?.id) {
      const stored = window.localStorage.getItem(pathStorageKey(user.id));
      if (isPathId(stored)) return stored;
    }
    return null;
  }, [searchParams, user?.id]);

  const source = useMemo<MigrantSource | null>(() => {
    const q = searchParams.get("source");
    if (isMigrantSource(q)) return q;
    // OAuth callback recovery: if we just came back from connecting a
    // provider but ?source= got lost (old tab with the pre-fix returnTo,
    // browser strip, whatever), infer it from ?connected= so the user
    // isn't trapped on "Pick a source first."
    const connected = searchParams.get("connected");
    if (connected === "github") return "github";
    if (connected === "notion") return "notion";
    if (connected === "google") return "drive";
    return null;
  }, [searchParams]);

  const stepIdx = useMemo(() => {
    const raw = searchParams.get("step");
    const parsed = raw ? parseInt(raw, 10) : 1;
    return Number.isFinite(parsed) && parsed > 0 ? parsed - 1 : 0;
  }, [searchParams]);

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

  // Reset the per-step canContinue gate on every step transition. Steps
  // that want to block call setCanContinue(false) in their own effects.
  useEffect(() => {
    setCanContinue(true);
  }, [stepIdx]);

  const pickPath = useCallback(
    (next: PathId) => {
      if (typeof window !== "undefined" && user?.id) {
        window.localStorage.setItem(pathStorageKey(user.id), next);
      }
      router.push(`/onboarding?path=${next}&step=1`);
    },
    [router, user?.id],
  );

  const pickSource = useCallback(
    (s: MigrantSource) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("source", s);
      const current = parseInt(params.get("step") ?? "1", 10) || 1;
      params.set("step", String(current + 1));
      router.push(`/onboarding?${params.toString()}`);
    },
    [router, searchParams],
  );

  const setSource = useCallback(
    (s: MigrantSource) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("source", s);
      router.push(`/onboarding?${params.toString()}`);
    },
    [router, searchParams],
  );

  const goToStep = useCallback(
    (idx: number) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("step", String(idx + 1));
      router.push(`/onboarding?${params.toString()}`);
    },
    [router, searchParams],
  );

  const skipToWorkspace = useCallback(() => {
    if (workspaceId) router.push(`/workspaces/${workspaceId}`);
    else router.push("/");
  }, [router, workspaceId]);

  if (loading || !apiKey) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        Loading…
      </div>
    );
  }

  // No path picked yet — show the chooser.
  if (!path) {
    return (
      <div className="min-h-screen flex flex-col">
        <Header user={user} onLogout={logout} />
        <IntentStep onPick={pickPath} />
      </div>
    );
  }

  const pathDef = PATHS[path];
  const totalSteps = pathDef.steps.length;
  const isDone = stepIdx >= totalSteps;

  async function finishAndExit() {
    if (workspaceId && user) {
      try {
        await seedWelcomePage({
          workspaceId,
          userId: user.id,
          displayName: user.display_name || user.name,
        });
      } catch {
        // Seeding is best-effort. If it fails (network, permission),
        // still redirect — the user can edit the description anytime.
      }
    }
    skipToWorkspace();
  }

  function nextStep() {
    if (stepIdx + 1 >= totalSteps) {
      if (pathDef.doneStep) {
        // Path has a Done UI — render it.
        goToStep(totalSteps);
      } else {
        // No Done UI — seed the welcome page and redirect to workspace.
        void finishAndExit();
      }
    } else {
      goToStep(stepIdx + 1);
    }
  }

  const stepCtx: StepCtx = {
    apiKey,
    workspaceId,
    source,
    pickSource,
    setSource,
    sharedUrl,
    setSharedUrl,
    onContinue: nextStep,
    onSkipAll: skipToWorkspace,
    canContinue,
    setCanContinue,
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 px-4 py-10">
        <div className="mx-auto w-full max-w-2xl space-y-8">
          <ProgressBar
            path={path}
            totalSteps={totalSteps}
            stepIdx={stepIdx}
            onJump={goToStep}
            isDone={isDone}
            showDone={!!pathDef.doneStep}
          />

          {isDone && pathDef.doneStep ? (
            <pathDef.doneStep workspaceId={workspaceId} />
          ) : (
            <>
              {renderStep(pathDef.steps[stepIdx], stepCtx)}
              <StepControls
                onContinue={nextStep}
                onSkipAll={skipToWorkspace}
                canContinue={canContinue}
              />
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function renderStep(
  Step: React.ComponentType<StepCtx>,
  ctx: StepCtx,
): React.ReactNode {
  return <Step {...ctx} />;
}

function ProgressBar({
  path,
  totalSteps,
  stepIdx,
  onJump,
  isDone,
  showDone,
}: {
  path: PathId;
  totalSteps: number;
  stepIdx: number;
  onJump: (idx: number) => void;
  isDone: boolean;
  showDone: boolean;
}) {
  const labels = Array.from({ length: totalSteps }, (_, i) => `Step ${i + 1}`);
  if (showDone) labels.push("Done");
  const currentIdx = isDone ? totalSteps : stepIdx;

  return (
    <div className="flex items-center gap-3">
      <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted">
        {PATHS[path].label}
      </div>
      <div className="flex items-center gap-2">
        {labels.map((label, i) => {
          const reached = i <= currentIdx;
          const isCurrent = i === currentIdx;
          return (
            <button
              key={label}
              type="button"
              onClick={() => onJump(i)}
              disabled={i > currentIdx}
              className={`flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.18em] transition-colors ${
                isCurrent
                  ? "text-foreground"
                  : reached
                    ? "text-muted hover:text-foreground"
                    : "text-muted/50"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isCurrent
                    ? "bg-brand"
                    : reached
                      ? "bg-foreground/40"
                      : "bg-border"
                }`}
              />
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function StepControls({
  onContinue,
  onSkipAll,
  canContinue,
}: {
  onContinue: () => void;
  onSkipAll: () => void;
  canContinue: boolean;
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
      <button
        type="button"
        onClick={onContinue}
        disabled={!canContinue}
        className="rounded-md bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-brand"
      >
        Continue
      </button>
    </div>
  );
}
