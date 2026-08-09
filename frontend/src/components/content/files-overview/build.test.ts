// The bird's-eye view promises two things: Memory renders as its own mount
// (never duplicated inside /files), and anything the API withheld surfaces as
// an explicit hidden count instead of silently vanishing.
import { describe, expect, it } from "vitest";
import { buildFilesNodes, buildSourceNodes } from "./build";
import type { FilesTree, SourceTreeEntry } from "@/lib/api";

const MEMORY_ID = "mem-folder";

const tree: FilesTree = {
  folders: [
    { id: "a", name: "Research", parent_folder_id: null, page_count: 1, file_count: 0 },
    { id: "b", name: "Papers", parent_folder_id: "a", page_count: 0, file_count: 1 },
    { id: MEMORY_ID, name: "Memory", parent_folder_id: null, page_count: 0, file_count: 0 },
    { id: "m1", name: "People", parent_folder_id: MEMORY_ID, page_count: 2, file_count: 0 },
  ],
  pages: [
    { id: "p1", name: "Notes", content_type: "markdown", folder_id: "a" },
    { id: "p2", name: "Root page", content_type: "markdown", folder_id: null },
  ],
  files: [
    {
      id: "f1", name: "spec.pdf", folder_id: "b", size_bytes: 2048,
      content_type: "application/pdf", url: null, created_at: "2026-01-01T00:00:00Z",
    },
  ],
};

describe("buildFilesNodes", () => {
  it("nests by parent id and splits Memory into its own mount", () => {
    const { files, memory } = buildFilesNodes(tree, MEMORY_ID);

    expect(files.map((n) => n.name)).toEqual(["Research", "Root page"]);
    const research = files[0];
    expect(research.children!.map((n) => n.name)).toEqual(["Papers", "Notes"]);
    expect(research.children![0].children![0]).toMatchObject({
      name: "spec.pdf",
      href: "/f/f1",
      annotation: "2 KB",
    });

    // Memory is a separate mount — not a folder row under /files.
    expect(files.some((n) => n.key === MEMORY_ID)).toBe(false);
    expect(memory.map((n) => n.name)).toEqual(["People"]);
  });
});

describe("buildSourceNodes", () => {
  it("turns truncation markers into hidden counts instead of rows", () => {
    const entries: SourceTreeEntry[] = [
      {
        name: "docs",
        kind: "folder",
        children: [
          { name: "api.md", kind: "file", path: "docs/api.md" },
          { name: "", kind: "truncated", hidden: 7 },
        ],
      },
      { name: "", kind: "truncated", hidden: 3 },
    ];

    const { nodes, hiddenCount } = buildSourceNodes(entries, "/sources/github");
    expect(hiddenCount).toBe(3);
    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toMatchObject({ name: "docs", kind: "folder", hiddenCount: 7 });
    // The annotation counts what's really there: 1 shown + 7 hidden.
    expect(nodes[0].annotation).toBe("8 items");
    expect(nodes[0].children![0]).toMatchObject({ name: "api.md", kind: "source-doc" });
  });
});
