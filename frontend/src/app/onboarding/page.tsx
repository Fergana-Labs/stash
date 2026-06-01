"use client";

import { Suspense, useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { track } from "../../lib/analytics";
import { addWorkspaceSource, getToken, listMyWorkspaces } from "../../lib/api";
import {
  listIntegrations,
  startConnect,
  type IntegrationProvider,
} from "../../lib/integrations";
import { seedWelcomePage } from "../../lib/onboarding/seedWelcome";

import MemoryAskStep from "./paths/memory/MemoryAskStep";

// The linear flow: connect a source, then ask the agent a real question over
// your data, then launch into the workspace. No intent picker, no paths.
const STEP_NAMES = ["connect", "ask"] as const;

// Providers shown in the connect step. Slack/Granola resolve their source's
// external_ref (workspace/team id) from the connected token, so we auto-add the
// source on connect; the tree sources (GitHub/Drive/Notion) need the user to
// pick a repo/folder/page, which they do from settings after onboarding.
const PROVIDERS: {
  key: IntegrationProvider;
  label: string;
  sourceType: string;
  autoAdd: boolean;
}[] = [
  { key: "github", label: "GitHub", sourceType: "github_repo", autoAdd: false },
  { key: "google", label: "Google Drive", sourceType: "google_drive", autoAdd: false },
  { key: "notion", label: "Notion", sourceType: "notion", autoAdd: false },
  { key: "slack", label: "Slack", sourceType: "slack", autoAdd: true },
  { key: "granola", label: "Granola", sourceType: "granola", autoAdd: true },
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
  const [connectedCount, setConnectedCount] = useState(0);

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
        if (workspaces.length > 0) setWorkspaceId(workspaces[0].id);
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
          userId: user.id,
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

  if (loading || !apiKey) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">Loading…</div>
    );
  }

  const isAsk = stepIdx >= 1;

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 px-4 py-10">
        <div className="mx-auto w-full max-w-2xl space-y-8">
          <ProgressBar stepIdx={stepIdx} />
          {isAsk ? (
            <AskStep workspaceId={workspaceId} />
          ) : (
            <ConnectStep
              workspaceId={workspaceId}
              onConnectedCount={setConnectedCount}
            />
          )}
          <StepControls
            onContinue={() => (isAsk ? void finishAndExit() : goToStep(1))}
            onSkip={skip}
            continueLabel={isAsk ? "Launch workspace" : "Continue"}
            canContinue={isAsk || connectedCount > 0}
          />
        </div>
      </main>
    </div>
  );
}

function ConnectStep({
  workspaceId,
  onConnectedCount,
}: {
  workspaceId: string | null;
  onConnectedCount: (n: number) => void;
}) {
  const searchParams = useSearchParams();
  const [statuses, setStatuses] = useState<Record<string, boolean>>({});

  const refresh = useCallback(async () => {
    try {
      const { providers } = await listIntegrations();
      const map: Record<string, boolean> = {};
      for (const p of providers) map[p.provider] = p.connected;
      setStatuses(map);
      onConnectedCount(Object.values(map).filter(Boolean).length);
    } catch {
      // Leave statuses as-is; the user can retry connecting.
    }
  }, [onConnectedCount]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Coming back from an OAuth callback (?connected=<provider>): refresh, and
  // for Slack/Granola add the workspace source now that the token exists.
  useEffect(() => {
    const connected = searchParams.get("connected");
    if (!connected || !workspaceId) return;
    const def = PROVIDERS.find((p) => p.key === connected);
    void (async () => {
      await refresh();
      if (def?.autoAdd) {
        try {
          await addWorkspaceSource(workspaceId, { source_type: def.sourceType });
        } catch {
          // Source may already exist (idempotent) — ignore.
        }
      }
    })();
  }, [searchParams, workspaceId, refresh]);

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
      <div className="space-y-2">
        {PROVIDERS.map((p) => {
          const connected = statuses[p.key];
          return (
            <div
              key={p.key}
              className="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3"
            >
              <span className="text-[14px] text-foreground">{p.label}</span>
              {connected ? (
                <span className="text-[12px] font-medium text-success">Connected ✓</span>
              ) : (
                <button
                  type="button"
                  onClick={() => void startConnect(p.key, "/onboarding")}
                  className="rounded-md border border-border px-3 py-1.5 text-[12px] text-foreground hover:bg-raised hover:border-brand"
                >
                  Connect
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AskStep({ workspaceId }: { workspaceId: string | null }) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Ask your agent
        </h1>
        <p className="text-sm text-dim max-w-md">
          Your agent can read everything you just connected, plus your files and past
          sessions. Ask it anything — it picks the right source.
        </p>
      </div>
      <MemoryAskStep workspaceId={workspaceId} />
    </div>
  );
}

function ProgressBar({ stepIdx }: { stepIdx: number }) {
  const labels = ["Connect", "Ask"];
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
