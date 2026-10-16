// Mock production data for the hill-climbing dashboard. There is no backend
// endpoint for per-agent daily reward yet; replace generateHillClimbData with
// an API call once one exists. Values are deterministic for a given day.

export type DailyReward = { day: number; mean: number; runs: number };

export type PromptChange = { day: number; version: number; note: string };

export type ClimbAgent = {
  id: string;
  name: string;
  rewardModel: string;
  daily: DailyReward[];
  promptChanges: PromptChange[];
};

export type ClimbRun = {
  id: string;
  agentId: string;
  task: string;
  finishedAt: number;
  reward: number;
  promptVersion: number;
  durationSec: number;
  steps: number;
};

export type HillClimbData = { now: number; days: number; dayStarts: number[]; agents: ClimbAgent[]; runs: ClimbRun[] };

const DAY = 86_400_000;

function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const clamp = (n: number) => Math.min(0.99, Math.max(0.02, n));

type Spec = {
  id: string; name: string; rewardModel: string; start: number; volume: number; noise: number;
  // Step changes in reward at a day offset from the start of history, each tied to a prompt version.
  steps: { at: number; delta: number; note: string }[];
  drift: number;
  tasks: string[];
};

const SPECS: Spec[] = [
  { id: "support-triage", name: "Support triage", rewardModel: "Resolution quality", start: 0.58, volume: 420, noise: 0.025, drift: 0.0004,
    steps: [{ at: 18, delta: 0.05, note: "Ask for order ID before escalating" }, { at: 51, delta: 0.04, note: "Cite the refund policy section" }, { at: 76, delta: 0.05, note: "Summarize prior tickets first" }],
    tasks: ["Route billing dispute", "Triage login failure", "Escalate outage report", "Tag shipping complaint", "Answer plan upgrade question"] },
  { id: "refund-resolver", name: "Refund resolver", rewardModel: "Policy compliance", start: 0.71, volume: 160, noise: 0.03, drift: 0,
    steps: [{ at: 30, delta: 0.03, note: "Check purchase date against window" }, { at: 82, delta: -0.11, note: "Shorter confirmation messages" }],
    tasks: ["Partial refund, damaged item", "Refund outside 30-day window", "Duplicate charge reversal", "Subscription proration"] },
  { id: "sql-analyst", name: "SQL analyst", rewardModel: "Answer correctness", start: 0.49, volume: 240, noise: 0.035, drift: 0.0012,
    steps: [{ at: 40, delta: 0.06, note: "Inspect schema before writing joins" }, { at: 70, delta: 0.07, note: "Validate row counts after filters" }],
    tasks: ["Weekly active users by plan", "Churn cohort, Q3", "Revenue by region", "Top failing API endpoints", "Trial-to-paid conversion"] },
  { id: "code-reviewer", name: "Code reviewer", rewardModel: "Review usefulness", start: 0.66, volume: 310, noise: 0.02, drift: 0.0001,
    steps: [{ at: 60, delta: 0.02, note: "Flag missing tests on changed paths" }],
    tasks: ["Review auth middleware PR", "Review migration PR", "Review flaky test fix", "Review API pagination PR"] },
  { id: "onboarding-guide", name: "Onboarding guide", rewardModel: "Activation reached", start: 0.62, volume: 95, noise: 0.045, drift: -0.0011,
    steps: [{ at: 64, delta: -0.03, note: "Skip workspace tour for invited users" }],
    tasks: ["Connect first data source", "Invite teammates", "Set up first dashboard", "Import CSV"] },
  { id: "invoice-extractor", name: "Invoice extractor", rewardModel: "Field accuracy", start: 0.8, volume: 520, noise: 0.012, drift: 0.0003,
    steps: [{ at: 25, delta: 0.03, note: "Normalize currency before totals" }, { at: 85, delta: 0.025, note: "Read line items from tables first" }],
    tasks: ["Extract vendor invoice #4471", "Extract multi-page invoice", "Extract scanned receipt", "Extract credit note"] },
];

export const HISTORY_DAYS = 90;

export function generateHillClimbData(now = Date.now()): HillClimbData {
  const today = new Date(now); today.setHours(0, 0, 0, 0);
  const dayStarts = Array.from({ length: HISTORY_DAYS }, (_, i) => today.getTime() - (HISTORY_DAYS - 1 - i) * DAY);
  const random = rng(Math.floor(today.getTime() / DAY));
  const agents: ClimbAgent[] = SPECS.map((spec) => {
    let level = spec.start;
    const daily: DailyReward[] = [];
    for (let day = 0; day < HISTORY_DAYS; day++) {
      for (const step of spec.steps) if (step.at === day) level += step.delta;
      level += spec.drift;
      const weekday = new Date(dayStarts[day]).getDay();
      const runs = Math.round(spec.volume * (weekday === 0 || weekday === 6 ? 0.45 : 1) * (0.85 + random() * 0.3));
      daily.push({ day, mean: clamp(level + (random() - 0.5) * 2 * spec.noise), runs });
    }
    return {
      id: spec.id, name: spec.name, rewardModel: spec.rewardModel, daily,
      promptChanges: spec.steps.map((s, i) => ({ day: s.at, version: i + 2, note: s.note })),
    };
  });

  const runs: ClimbRun[] = [];
  agents.forEach((agent, a) => {
    const spec = SPECS[a];
    const latest = agent.daily.at(-1)!.mean;
    const version = agent.promptChanges.length + 1;
    const count = 8 + Math.round(random() * 6);
    for (let i = 0; i < count; i++) {
      const finishedAt = now - Math.round(random() * 20 * 3_600_000);
      const tail = random() < 0.12 ? -0.35 : 0;
      runs.push({
        id: `${agent.id}-${i}`, agentId: agent.id, task: spec.tasks[Math.floor(random() * spec.tasks.length)], finishedAt,
        reward: clamp(latest + tail + (random() - 0.5) * 0.24), promptVersion: version,
        durationSec: Math.round(20 + random() * 260), steps: Math.round(4 + random() * 30),
      });
    }
  });
  runs.sort((a, b) => b.finishedAt - a.finishedAt);
  return { now, days: HISTORY_DAYS, dayStarts, agents, runs };
}

/** Run-weighted mean reward over a span of days [from, to). */
export function meanReward(daily: DailyReward[], from: number, to: number) {
  let sum = 0, n = 0;
  for (const d of daily) if (d.day >= from && d.day < to) { sum += d.mean * d.runs; n += d.runs; }
  return n ? sum / n : null;
}

export function totalRuns(daily: DailyReward[], from: number, to: number) {
  return daily.reduce((n, d) => (d.day >= from && d.day < to ? n + d.runs : n), 0);
}

/** Daily run-weighted mean across all agents. */
export function fleetDaily(agents: ClimbAgent[], days: number): DailyReward[] {
  return Array.from({ length: days }, (_, day) => {
    let sum = 0, runs = 0;
    for (const a of agents) { sum += a.daily[day].mean * a.daily[day].runs; runs += a.daily[day].runs; }
    return { day, mean: runs ? sum / runs : 0, runs };
  });
}
