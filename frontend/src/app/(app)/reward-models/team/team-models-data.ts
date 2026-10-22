// Mock data for the team reward models page. There is no backend endpoint for
// team-shared reward models yet; replace this module with an API call when one exists.

export type Teammate = { id: string; name: string; initials: string };

export type TeamRewardModel = {
  id: string;
  name: string;
  description: string;
  ownerId: string;
  /** Share of held-out examples where the model's verdict matched the person's label. */
  agreement: number;
  heldOut: number;
  /** Agents (any owner) currently scored by this model. */
  agents: string[];
  updatedAt: string;
  lastChange: string;
  shared: boolean;
};

export const ME = "henry";

export const TEAMMATES: Record<string, Teammate> = {
  henry: { id: "henry", name: "Henry Dowling", initials: "HD" },
  coleman: { id: "coleman", name: "Coleman Hindes", initials: "CH" },
  sam: { id: "sam", name: "Sam Ortiz", initials: "SO" },
  priya: { id: "priya", name: "Priya Raman", initials: "PR" },
  mike: { id: "mike", name: "Mike Feld", initials: "MF" },
};

/** Agents the signed-in person owns, which can adopt a reward model. */
export const MY_AGENTS = ["Support triage", "Parts lookup", "Release notes writer"];

export const TEAM_MODELS: TeamRewardModel[] = [
  {
    id: "rm_support_tone",
    name: "Support reply tone",
    description: "Scores customer replies for a calm, direct tone: answers the question in the first sentence, no filler apologies, no promises about dates.",
    ownerId: "priya",
    agreement: 0.91,
    heldOut: 140,
    agents: ["Support triage", "Billing assistant", "Onboarding emails"],
    updatedAt: "2026-10-14T16:20:00Z",
    lastChange: "Added 22 examples of replies that over-apologize",
    shared: true,
  },
  {
    id: "rm_part_match",
    name: "Part number match",
    description: "Checks that a recommended part fits the vehicle in the request: VIN-decoded model year, engine, and axle all agree with the part's fitment.",
    ownerId: "sam",
    agreement: 0.88,
    heldOut: 96,
    agents: ["Parts lookup", "Quote builder"],
    updatedAt: "2026-10-15T09:05:00Z",
    lastChange: "Retrained after fixing mislabeled axle examples",
    shared: true,
  },
  {
    id: "rm_pr_review",
    name: "PR review usefulness",
    description: "Rates code review comments by whether they point at a real defect with a concrete fix, rather than style nits or restating the diff.",
    ownerId: "coleman",
    agreement: 0.84,
    heldOut: 210,
    agents: ["Code reviewer"],
    updatedAt: "2026-10-09T21:40:00Z",
    lastChange: "Raised the bar for nit-only comments",
    shared: true,
  },
  {
    id: "rm_sql_safety",
    name: "Read-only SQL",
    description: "Fails any agent step that issues a write, DDL, or unbounded scan against a production database.",
    ownerId: "mike",
    agreement: 0.97,
    heldOut: 64,
    agents: ["Data analyst", "Usage reports", "Support triage", "Ops on-call"],
    updatedAt: "2026-09-30T13:12:00Z",
    lastChange: "Now catches COPY and TRUNCATE",
    shared: true,
  },
  {
    id: "rm_summary_faithful",
    name: "Meeting summary faithfulness",
    description: "Checks that every decision and owner in a meeting summary appears in the transcript, and that nothing in the summary contradicts it.",
    ownerId: "priya",
    agreement: 0.79,
    heldOut: 58,
    agents: ["Meeting notes"],
    updatedAt: "2026-10-02T11:00:00Z",
    lastChange: "First version",
    shared: true,
  },
  {
    id: "rm_landing_taste",
    name: "Landing page taste",
    description: "Henry's design judgment on marketing pages: hierarchy, restraint, and copy that names concrete things.",
    ownerId: "henry",
    agreement: 0.86,
    heldOut: 120,
    agents: ["Release notes writer"],
    updatedAt: "2026-10-16T08:30:00Z",
    lastChange: "Added 30 bad examples from the September redesign",
    shared: true,
  },
  {
    id: "rm_changelog",
    name: "Changelog clarity",
    description: "Scores changelog entries on whether a customer can tell what changed for them without reading the PR.",
    ownerId: "henry",
    agreement: 0.72,
    heldOut: 40,
    agents: [],
    updatedAt: "2026-10-11T18:45:00Z",
    lastChange: "First version",
    shared: false,
  },
];
