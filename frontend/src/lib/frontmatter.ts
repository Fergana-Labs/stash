// A page's leading `---` frontmatter block is machine-readable metadata
// (skills live and die by it). The rich editor cannot represent it — a
// markdown renderer parses `key: value` above `---` as a heading — so the
// editor splits it off before rendering and reattaches it on save. The
// editor never sees it; it can never corrupt it.

export type SplitMarkdown = { frontmatter: string | null; body: string };

export function splitFrontmatter(markdown: string): SplitMarkdown {
  if (!markdown.startsWith("---\n") && markdown !== "---") {
    return { frontmatter: null, body: markdown };
  }
  const end = markdown.indexOf("\n---", 4);
  if (end === -1) return { frontmatter: null, body: markdown };
  const afterFence = end + 4;
  const rest = markdown.slice(afterFence);
  // The closing fence must be a whole line: "---\n" or "---" at EOF.
  if (rest !== "" && !rest.startsWith("\n")) return { frontmatter: null, body: markdown };
  const block = markdown.slice(4, end);
  // A document that opens with a horizontal rule also matches the fences.
  // Frontmatter is key/value lines, so require the first non-empty line to
  // look like one — otherwise the author's opening paragraph would be hidden
  // in the read-only metadata strip and become uneditable.
  const firstLine = block.split("\n").find((line) => line.trim() !== "") ?? "";
  if (!/^[A-Za-z_][\w-]*\s*:/.test(firstLine)) return { frontmatter: null, body: markdown };
  return {
    frontmatter: block,
    body: rest.replace(/^\n+/, ""),
  };
}

export function joinFrontmatter(frontmatter: string | null, body: string): string {
  if (frontmatter === null) return body;
  return `---\n${frontmatter}\n---\n\n${body}`;
}
