import type { SessionSummary } from "./api";

export type SessionDayGroup = {
  key: string;
  label: string;
  count: number;
  users: { user: string; sessions: SessionSummary[] }[];
};

export function requireSessionUserName(value: string | null | undefined): string {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) throw new Error("Session author display_name is missing");
  return trimmed;
}

export function groupSessionsByDayAndUser(sessions: SessionSummary[]): SessionDayGroup[] {
  const days = new Map<string, Map<string, SessionSummary[]>>();
  for (const session of sortedSessions(sessions)) {
    const dayKey = sessionDayKey(session.last_event_at || session.started_at);
    const user = requireSessionUserName(session.user_name);
    if (!days.has(dayKey)) days.set(dayKey, new Map());
    const users = days.get(dayKey)!;
    users.set(user, [...(users.get(user) ?? []), session]);
  }

  return Array.from(days.entries()).map(([key, users]) => {
    const buckets = Array.from(users.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([user, rows]) => ({
        user,
        sessions: rows,
      }));

    return {
      key,
      label: formatSessionDay(key),
      count: buckets.reduce((sum, bucket) => sum + bucket.sessions.length, 0),
      users: buckets,
    };
  });
}

function sortedSessions(sessions: SessionSummary[]): SessionSummary[] {
  return [...sessions].sort((a, b) => {
    const timeDiff = sessionTime(b) - sessionTime(a);
    if (timeDiff !== 0) return timeDiff;

    const userA = requireSessionUserName(a.user_name);
    const userB = requireSessionUserName(b.user_name);
    const userDiff = userA.localeCompare(userB);
    if (userDiff !== 0) return userDiff;

    return a.session_id.localeCompare(b.session_id);
  });
}

function sessionTime(session: SessionSummary): number {
  const time = new Date(session.last_event_at || session.started_at).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function sessionDayKey(iso: string | null): string {
  if (!iso) return "Unknown date";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Unknown date";
  return date.toISOString().slice(0, 10);
}

function formatSessionDay(key: string): string {
  if (key === "Unknown date") return key;
  return new Date(`${key}T12:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}

// Flat-axis groupings for the sessions index "View by" control. Same shape
// as SessionDayGroup so the page can render any of them through one
// component path.

export type SessionFlatGroup = {
  key: string;
  label: string;
  count: number;
  sessions: SessionSummary[];
};

export function groupSessionsByUser(sessions: SessionSummary[]): SessionFlatGroup[] {
  return groupBy(sessions, (s) => requireSessionUserName(s.user_name));
}

export function groupSessionsByAgent(sessions: SessionSummary[]): SessionFlatGroup[] {
  return groupBy(sessions, (s) => (s.agent_name || "").trim() || "Unknown agent");
}

// Groups + sorts: largest groups first, sessions inside groups reverse-chronological.
function groupBy(
  sessions: SessionSummary[],
  keyFn: (s: SessionSummary) => string
): SessionFlatGroup[] {
  const buckets = new Map<string, SessionSummary[]>();
  for (const s of sortedSessions(sessions)) {
    const k = keyFn(s);
    buckets.set(k, [...(buckets.get(k) ?? []), s]);
  }
  return Array.from(buckets.entries())
    .map(([key, rows]) => ({ key, label: key, count: rows.length, sessions: rows }))
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}
