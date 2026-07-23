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

import { citationFor, getAgentChat } from "./agentChat";

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

describe("citationFor link targets", () => {
  it("links a stash search to the app search page", () => {
    expect(citationFor("Bash", { command: 'stash search "vector recall"' })).toEqual({
      label: 'stash search "vector recall"',
      href: "/search?q=vector%20recall",
    });
  });

  it("links a stash page read straight to the page", () => {
    const id = "0b5c2f6e-9d31-4a7e-8f00-1234567890ab";
    expect(citationFor("Bash", { command: `stash read ${id}` })?.href).toBe(`/p/${id}`);
  });

  it("carries a VFS cat path for click-time resolution", () => {
    expect(citationFor("Bash", { command: "stash vfs \"cat '/files/Runbook.md'\"" })).toEqual({
      label: "stash vfs \"cat '/files/Runbook.md'\"",
      vfsPath: "/files/Runbook.md",
    });
  });

  it("links a web fetch to the fetched URL", () => {
    expect(citationFor("WebFetch", { url: "https://example.com/post" })).toEqual({
      label: "example.com",
      href: "https://example.com/post",
    });
  });

  it("leaves sprite-local reads unlinked", () => {
    expect(citationFor("Read", { file_path: "/home/user/work/notes.md" })).toEqual({
      label: "notes.md",
    });
  });
});
