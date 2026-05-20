import type { ComponentType } from "react";

import MigrantSourceStep from "@/app/onboarding/paths/migrant/MigrantSourceStep";
import MigrantImportStep from "@/app/onboarding/paths/migrant/MigrantImportStep";
import MigrantDemoStep from "@/app/onboarding/paths/migrant/MigrantDemoStep";
import MemoryImportStep from "@/app/onboarding/paths/memory/MemoryImportStep";
import MemoryAskStep from "@/app/onboarding/paths/memory/MemoryAskStep";
import MemorySearchStep from "@/app/onboarding/paths/memory/MemorySearchStep";
import SharingDropStep from "@/app/onboarding/paths/sharing/SharingDropStep";
import SharingBrowseStep from "@/app/onboarding/paths/sharing/SharingBrowseStep";
import SharingHandoffStep from "@/app/onboarding/paths/sharing/SharingHandoffStep";
import InviteStep from "@/app/onboarding/steps/InviteStep";
import DoneStep from "@/app/onboarding/steps/DoneStep";

export type PathId = "migrant" | "memory" | "sharing";

export type MigrantSource = "notion" | "obsidian" | "github" | "drive";

export type StepCtx = {
  apiKey: string;
  workspaceId: string | null;
  // Sub-source on the migrant path, threaded via ?source=. null elsewhere.
  source: MigrantSource | null;
  // Picks a source AND advances one step in a single navigation. Using two
  // separate router.pushes (set source, then continue) loses the source —
  // the second push reads a stale searchParams closure.
  pickSource: (s: MigrantSource) => void;
  // Sets the source without changing step — used by paths that have no
  // dedicated source-picker step but still need to branch on source
  // (e.g. memory path's import gate).
  setSource: (s: MigrantSource) => void;
  // Set by SharingDropStep / FirstShareStep when /publish returns a URL —
  // surfaces in DoneStep + welcome page.
  sharedUrl: string | null;
  setSharedUrl: (url: string) => void;
  onContinue: () => void;
  onSkip: () => void;
  onSkipAll: () => void;
};

export type PathDef = {
  id: PathId;
  label: string;
  steps: ComponentType<StepCtx>[];
  doneStep: ComponentType<{ workspaceId: string | null }>;
};

// Each path's tail (Invite + Done) is shared. The existing InviteStep
// component takes its own props shape, so paths.ts wraps it to match
// StepCtx in the page.tsx renderer.
export const PATHS: Record<PathId, PathDef> = {
  migrant: {
    id: "migrant",
    label: "Knowledge base",
    steps: [
      MigrantSourceStep,
      MigrantImportStep,
      MigrantDemoStep,
      wrapInvite(InviteStep),
    ],
    doneStep: DoneStep,
  },
  memory: {
    id: "memory",
    label: "Agent memory",
    steps: [MemoryImportStep, MemoryAskStep, MemorySearchStep, wrapInvite(InviteStep)],
    doneStep: DoneStep,
  },
  sharing: {
    id: "sharing",
    label: "Artifacts",
    steps: [SharingDropStep, SharingBrowseStep, SharingHandoffStep],
    doneStep: DoneStep,
  },
};

// InviteStep takes {workspaceId} only — wrap to satisfy the path step contract.
function wrapInvite(Step: ComponentType<{ workspaceId: string | null }>) {
  const Wrapped: ComponentType<StepCtx> = ({ workspaceId }) => (
    <Step workspaceId={workspaceId} />
  );
  Wrapped.displayName = "InviteStepWrapped";
  return Wrapped;
}
