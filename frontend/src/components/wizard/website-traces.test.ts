import { describe, expect, it } from "vitest";
import { compactSession, pickTraceFiles } from "./website-traces";

const entry = (path: string, size = 10, lastModified = 0) => ({
  path,
  file: { name: path.split("/").pop()!, size, lastModified } as File,
});

describe("pickTraceFiles", () => {
  it("keeps sessions inside Claude Code and Codex history folders, newest first", () => {
    const { kept, skipped } = pickTraceFiles([
      entry(".claude/projects/site/old.jsonl", 10, 1),
      entry(".codex/sessions/2026/rollout-new.jsonl", 10, 2),
      entry(".claude/projects/site/.DS_Store"),
      entry("projects/.git/config.jsonl"),
      entry("notes.md"),
      entry("huge.jsonl", 500_000_000),
    ]);
    expect(kept.map((k) => k.path)).toEqual([".codex/sessions/2026/rollout-new.jsonl", ".claude/projects/site/old.jsonl"]);
    expect(skipped).toHaveLength(4);
  });

  it("caps the number of files, dropping the oldest", () => {
    const many = Array.from({ length: 205 }, (_, i) => entry(`s${i}.jsonl`, 10, i));
    const { kept, skipped } = pickTraceFiles(many);
    expect(kept).toHaveLength(200);
    expect(skipped).toEqual(["s4.jsonl", "s3.jsonl", "s2.jsonl", "s1.jsonl", "s0.jsonl"]);
  });
});

describe("compactSession", () => {
  it("keeps messages and tool calls, clips tool output, and drops everything else", async () => {
    const lines = [
      { type: "session_meta", payload: { id: "s" } },
      { type: "compacted", payload: { message: "x".repeat(1000) } },
      { type: "event_msg", payload: { type: "token_count" } },
      { type: "response_item", payload: { type: "reasoning", summary: [] } },
      { type: "response_item", payload: { type: "message", role: "user", content: [{ type: "input_image", image_url: "data:image/png;base64,AAAA" }] } },
      { type: "response_item", payload: { type: "function_call_output", call_id: "c", output: "y".repeat(10_000) } },
    ].map((l) => JSON.stringify(l));
    const kept = (await compactSession(lines.join("\n"))).split("\n").map((l) => JSON.parse(l));
    expect(kept.map((r) => r.payload.type ?? r.type)).toEqual(["session_meta", "message", "function_call_output"]);
    expect(kept[1].payload.content[0].image_url).toBe("data:image/png;base64,AAAA");
    expect(kept[2].payload.output).toHaveLength(4000);
  });
});
