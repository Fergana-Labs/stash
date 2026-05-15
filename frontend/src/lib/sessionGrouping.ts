import type { SessionSummary } from "./api";

export type SessionDayGroup = {
  key: string;
  label: string;
  count: number;
  users: { user: string; sessions: SessionSummary[] }[];
};

export function displaySessionUserName(
  value: string | null | undefined,
  fallback = "Unknown user"
): string {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) return fallback;
  return trimmed.toLowerCase() === "codex" ? "Sam" : trimmed;
}

export function groupSessionsByDayAndUser(sessions: SessionSummary[]): SessionDayGroup[] {
  const days = new Map<string, Map<string, SessionSummary[]>>();
  for (const session of sortedSessions(sessions)) {
    const dayKey = sessionDayKey(session.last_event_at || session.started_at);
    const user = displaySessionUserName(session.user_name || session.agent_name, "Unknown user");
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

    const userA = displaySessionUserName(a.user_name || a.agent_name, "");
    const userB = displaySessionUserName(b.user_name || b.agent_name, "");
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
