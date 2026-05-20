import { describe, expect, it } from "vitest";
import type { SessionSummary } from "./api";
import {
  groupSessionsByAgent,
  groupSessionsByDayAndUser,
  groupSessionsByUser,
  requireSessionUserName,
} from "./sessionGrouping";

function session(fields: Partial<SessionSummary> & { session_id: string }): SessionSummary {
  return {
    session_id: fields.session_id,
    title: fields.title ?? fields.session_id,
    workspace_id: "ws-1",
    workspace_name: "Workspace",
    user_name: fields.user_name ?? "Test User",
    agent_name: fields.agent_name ?? null,
    event_count: fields.event_count ?? 1,
    started_at: fields.started_at ?? "2026-05-14T09:00:00Z",
    last_event_at: fields.last_event_at ?? fields.started_at ?? "2026-05-14T09:00:00Z",
  };
}

describe("groupSessionsByDayAndUser", () => {
  it("sorts sessions by day, then user, then recency", () => {
    const grouped = groupSessionsByDayAndUser([
      session({
        session_id: "older",
        user_name: "Zoe",
        last_event_at: "2026-05-13T12:00:00Z",
      }),
      session({
        session_id: "newer",
        user_name: "Ada",
        last_event_at: "2026-05-14T12:00:00Z",
      }),
      session({
        session_id: "newest",
        user_name: "Ada",
        last_event_at: "2026-05-14T13:00:00Z",
      }),
      session({
        session_id: "same-day-other-user",
        user_name: "Ben",
        last_event_at: "2026-05-14T11:00:00Z",
      }),
    ]);

    expect(grouped.map((day) => day.key)).toEqual(["2026-05-14", "2026-05-13"]);
    expect(grouped[0].users.map((bucket) => bucket.user)).toEqual(["Ada", "Ben"]);
    expect(grouped[0].users[0].sessions.map((row) => row.session_id)).toEqual([
      "newest",
      "newer",
    ]);
  });
});

describe("groupSessionsByUser", () => {
  it("groups by user_name, largest-bucket-first, reverse-chronological inside", () => {
    const grouped = groupSessionsByUser([
      session({ session_id: "ada-old", user_name: "Ada", last_event_at: "2026-05-13T12:00:00Z" }),
      session({ session_id: "ada-new", user_name: "Ada", last_event_at: "2026-05-14T13:00:00Z" }),
      session({ session_id: "ben", user_name: "Ben", last_event_at: "2026-05-14T12:00:00Z" }),
    ]);
    expect(grouped.map((g) => g.key)).toEqual(["Ada", "Ben"]);
    expect(grouped[0].sessions.map((s) => s.session_id)).toEqual(["ada-new", "ada-old"]);
  });

  it("fails when a session is missing the author's display name", () => {
    expect(() => requireSessionUserName(null)).toThrow(
      "Session author display_name is missing"
    );
  });
});

describe("groupSessionsByAgent", () => {
  it("groups by agent_name and labels unknown buckets explicitly", () => {
    const grouped = groupSessionsByAgent([
      session({ session_id: "c1", agent_name: "codex" }),
      session({ session_id: "c2", agent_name: "codex" }),
      session({ session_id: "u1", agent_name: null }),
    ]);
    expect(grouped.map((g) => g.key)).toEqual(["codex", "Unknown agent"]);
    expect(grouped[0].count).toBe(2);
  });
});
