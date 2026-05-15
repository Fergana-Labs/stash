import { describe, expect, it } from "vitest";
import type { SessionSummary } from "./api";
import { groupSessionsByDayAndUser } from "./sessionGrouping";

function session(fields: Partial<SessionSummary> & { session_id: string }): SessionSummary {
  return {
    session_id: fields.session_id,
    workspace_id: "ws-1",
    workspace_name: "Workspace",
    user_name: fields.user_name ?? null,
    agent_name: fields.agent_name ?? null,
    event_count: fields.event_count ?? 1,
    started_at: fields.started_at ?? "2026-05-14T09:00:00Z",
    last_event_at: fields.last_event_at ?? fields.started_at ?? "2026-05-14T09:00:00Z",
    first_prompt_preview: fields.first_prompt_preview ?? null,
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
