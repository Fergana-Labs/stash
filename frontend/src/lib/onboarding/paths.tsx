// Onboarding shared types. The 3-path intent wizard was replaced by a single
// linear Connect → Ask flow (see app/onboarding/page.tsx); only the Ask step's
// prop contract remains.

// The Ask step's prop contract. The scope is the current user; no props needed.
export type StepCtx = Record<string, never>;
