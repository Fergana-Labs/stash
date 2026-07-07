// Restoring a chat tab folds stored tool rows into the citations of the
// assistant message that follows them — the same strip the live SSE stream
// builds turn by turn, so a reopened tab looks like the run did live.

import { describe, expect, it, vi } from "vitest";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({
  API_BASE: "",
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  getAuthToken: () => "k",
}));

import { getAgentChat } from "./agentChat";

describe("getAgentChat", () => {
  it("folds tool rows into the next assistant message's citations", async () => {
    apiFetch.mockResolvedValueOnce({
      messages: [
        { role: "user", content: "curate" },
        {
          role: "tool",
          content: "Ran: stash changes --json",
          tool_name: "Bash",
          metadata: { command: "stash changes --json" },
        },
        {
          role: "tool",
          content: "Read /memory/index.md",
          tool_name: "Read",
          metadata: { file_path: "/memory/index.md" },
        },
        { role: "assistant", content: "done" },
      ],
    });

    const messages = await getAgentChat("agent-curate-1");

    expect(messages).toHaveLength(2);
    expect(messages[0]).toEqual({ role: "user", content: "curate" });
    expect(messages[1].role).toBe("assistant");
    expect(messages[1].citations?.map((c) => c.label)).toEqual([
      "stash changes --json",
      "index.md",
    ]);
  });

  it("parses generic args_preview and skips unciteable tools", async () => {
    apiFetch.mockResolvedValueOnce({
      messages: [
        { role: "user", content: "hi" },
        {
          role: "tool",
          content: 'Grep: {"pattern": "quokka"}',
          tool_name: "Grep",
          metadata: { args_preview: '{"pattern": "quokka"}' },
        },
        {
          role: "tool",
          content: "Edited /tmp/x",
          tool_name: "Edit",
          metadata: { file_path: "/tmp/x" },
        },
        { role: "assistant", content: "found" },
      ],
    });

    const messages = await getAgentChat("s1");

    // Grep grounds the answer; an Edit is work, not grounding.
    expect(messages[1].citations?.map((c) => c.label)).toEqual(['search "quokka"']);
  });
});
