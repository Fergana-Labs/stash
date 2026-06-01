// Onboarding shared types. The 3-path intent wizard was replaced by a single
// linear Connect → Ask flow (see app/onboarding/page.tsx); only these types
// remain, used by the Ask step and the welcome-page seeder.

export type PathId = "migrant" | "memory" | "sharing";

export type MigrantSource = "notion" | "obsidian" | "github" | "drive";

// The Ask step's prop contract — just the workspace it operates in.
export type StepCtx = {
  workspaceId: string | null;
};
