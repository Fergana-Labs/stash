/** Scheduled runs (Memory curator, other scheduled agents) have no human
 * turns: their "user" events are server-built prompts. Labelling them as a
 * person misleads anyone auditing a trace, so the viewer must call them what
 * they are — the system prompt — while real chat turns keep the human's name.
 */
import { describe, expect, it } from "vitest";
import type { SessionEvent } from "@/lib/api";
import { eventToTurn, isScheduledRunSession, toolDisplay } from "./transcript";

function event(overrides: Partial<SessionEvent>): SessionEvent {
  return {
    id: "ev-1",
    role: "user",
    agent_name: "",
    content: "hello",
    tool_name: null,
    created_at: null,
    ...overrides,
  };
}

describe("system prompt labelling", () => {
  it("labels user events in a curator run as the system prompt", () => {
    const turn = eventToTurn(
      event({ content: "You maintain the user's Memory wiki…" }),
      "agent-curate-123-20260818",
      "Henry"
    );
    expect(turn.who).toBe("system");
    expect(turn.name).toBe("System prompt");
  });

  it("labels user events in a scheduled agent run as the system prompt", () => {
    const turn = eventToTurn(event({}), "agent-sched-abc-20260818", null);
    expect(turn.who).toBe("system");
  });

  it("keeps real user turns human, named after the session author", () => {
    const turn = eventToTurn(event({}), "claude-code-session-1", "Henry");
    expect(turn.who).toBe("user");
    expect(turn.name).toBe("Henry");
  });

  it("falls back to a generic label when no author name is recorded", () => {
    const turn = eventToTurn(event({}), "claude-code-session-1", null);
    expect(turn.name).toBe("user");
  });

  it("names assistant turns after the agent", () => {
    const turn = eventToTurn(
      event({ role: "assistant", agent_name: "Memory curator" }),
      "agent-curate-123-20260818",
      null
    );
    expect(turn.who).toBe("assistant");
    expect(turn.name).toBe("Memory curator");
  });

  it("recognises only curate/sched session ids as scheduled runs", () => {
    expect(isScheduledRunSession("agent-curate-x-1")).toBe(true);
    expect(isScheduledRunSession("agent-sched-x-1")).toBe(true);
    expect(isScheduledRunSession("agent-chat-x-1")).toBe(false);
    expect(isScheduledRunSession("my-session")).toBe(false);
  });
});

describe("toolDisplay", () => {
  it("shows a bash call's command as the code, summarized by its description", () => {
    const { summary, body } = toolDisplay(
      '{"command": "stash memory --json", "description": "Read the memory folder id"}'
    );
    expect(summary).toBe("Read the memory folder id");
    expect(body).toBe("stash memory --json");
  });

  it("pretty-prints other JSON inputs and summarizes by file_path", () => {
    const { summary, body } = toolDisplay('{"file_path": "/tmp/clip.txt"}');
    expect(summary).toBe("/tmp/clip.txt");
    expect(body).toBe('{\n  "file_path": "/tmp/clip.txt"\n}');
  });

  it("passes non-JSON content through untouched", () => {
    const { summary, body } = toolDisplay("plain tool output");
    expect(summary).toBe("plain tool output");
    expect(body).toBe("plain tool output");
  });

  it("truncates long summaries to one line", () => {
    const { summary } = toolDisplay("line one\nline two " + "x".repeat(300));
    expect(summary).not.toContain("\n");
    expect(summary.length).toBeLessThanOrEqual(121);
  });
});
