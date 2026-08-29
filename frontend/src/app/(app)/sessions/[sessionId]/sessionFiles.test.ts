import { describe, expect, it } from "vitest";
import type { SessionArtifact } from "@/lib/api";
import { sessionFileRows } from "./sessionFiles";

const artifact: SessionArtifact = {
  id: "artifact-1",
  file_path: "backend/main.py",
  size_bytes: 100,
  url: "https://files.test/main.py",
  created_at: "2026-08-26T00:00:00Z",
};

describe("sessionFileRows", () => {
  it("links a touched path only to its exact archived artifact", () => {
    const rows = sessionFileRows(
      ["backend/main.py", "frontend/main.py"],
      [artifact],
      "/workspace/stash"
    );

    expect(rows[0].artifact).toBe(artifact);
    expect(rows[1].artifact).toBeUndefined();
  });

  it("matches an absolute touched path to the artifact path relative to the session cwd", () => {
    const [row] = sessionFileRows(
      ["/workspace/stash/backend/main.py"],
      [artifact],
      "/workspace/stash"
    );

    expect(row.artifact).toBe(artifact);
  });

  it("includes uploaded artifacts that were not present in touched-file metadata", () => {
    expect(sessionFileRows([], [artifact], "/workspace/stash")).toEqual([
      { path: "backend/main.py", artifact },
    ]);
  });
});
