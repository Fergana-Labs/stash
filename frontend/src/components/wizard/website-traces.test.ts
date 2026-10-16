import { describe, expect, it } from "vitest";
import { pickTraceFiles } from "./website-traces";

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
      entry("huge.jsonl", 9_000_000),
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
