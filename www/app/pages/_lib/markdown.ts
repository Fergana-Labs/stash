// Markdown ↔ ProseMirror JSON round-trip, copied from the product app's
// MarkdownEditor (frontend/src/components/workspace/MarkdownEditor.tsx)
// minus the comment-anchor marks and user-file image URLs, which
// don't exist on the public pastebin.

export type JSONNode = {
  type?: string;
  text?: string;
  marks?: Array<{ type: string; attrs?: Record<string, string> }>;
  attrs?: Record<string, unknown>;
  content?: JSONNode[];
};

function isSupportedImageUrl(url: string): boolean {
  return /^https?:\/\//i.test(url);
}

// Stash-authored markdown can carry inline comment anchors; the pastebin
// has no comments, so unwrap them to their inner text before parsing.
const COMMENT_SPAN_RE = /<span\s+data-comment-id="[^"]+">([\s\S]*?)<\/span>/g;

function parseInlineMarkdown(text: string): JSONNode[] {
  // Empty inputs (e.g. a bullet line that's just "-   ") must not produce
  // a {type: "text", text: ""} node — prosemirror rejects empty text nodes
  // and the whole document fails to render.
  if (!text) return [];
  const nodes = parseInlineMarkdownInner(text.replace(COMMENT_SPAN_RE, "$1"));
  return nodes.filter(
    (n) => n.type !== "text" || (typeof n.text === "string" && n.text.length > 0),
  );
}

function parseInlineMarkdownInner(text: string): JSONNode[] {
  // Inline grammar, ordered by priority:
  //   [[bracketed text]]       — plain text
  //   [![alt](src)](href)      — image inside a link (matched before plain image
  //                              so the outer brackets don't swallow the image)
  //   ![alt](src)              — image node (absolute URLs only)
  //   [text](url)              — link mark
  //   **bold**                 — bold mark
  //   *italic*                 — italic mark
  //   `code`                   — code mark
  const inlinePattern =
    /(\[\[([^\]]+)\]\]|\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)|!\[([^\]]*)\]\(([^)]+)\)|\[([^\]]+)\]\(([^)]+)\)|\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g;
  const nodes: JSONNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = inlinePattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push({ type: "text", text: text.slice(lastIndex, match.index) });
    }

    if (match[2] !== undefined) {
      // No bracket-link syntax here; bracket refs stay plain.
      nodes.push({ type: "text", text: match[0] });
    } else if (match[3] !== undefined) {
      // [![alt](src)](href) — linked image. Render as the image; the href
      // is preserved as the image's title so it isn't silently dropped.
      const alt = match[3];
      const src = match[4];
      const href = match[5];
      if (isSupportedImageUrl(src)) {
        nodes.push({ type: "image", attrs: { src, alt, title: href } });
      } else {
        nodes.push({ type: "text", text: match[0] });
      }
    } else if (match[6] !== undefined) {
      // ![alt](src)
      const alt = match[6];
      const src = match[7];
      if (isSupportedImageUrl(src)) {
        nodes.push({ type: "image", attrs: { src, alt } });
      } else {
        // Keep the raw markdown visible so it isn't silently lost.
        nodes.push({ type: "text", text: match[0] });
      }
    } else if (match[8] !== undefined) {
      // [text](url)
      nodes.push({
        type: "text",
        text: match[8],
        marks: [{ type: "link", attrs: { href: match[9] } }],
      });
    } else if (match[10] !== undefined) {
      // **bold**
      nodes.push({ type: "text", text: match[10], marks: [{ type: "bold" }] });
    } else if (match[11] !== undefined) {
      // *italic*
      nodes.push({ type: "text", text: match[11], marks: [{ type: "italic" }] });
    } else if (match[12] !== undefined) {
      // `code`
      nodes.push({ type: "text", text: match[12], marks: [{ type: "code" }] });
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    nodes.push({ type: "text", text: text.slice(lastIndex) });
  }

  return nodes.length > 0 ? nodes : [{ type: "text", text }];
}

export function markdownToInitialJSON(markdown: string): JSONNode {
  if (!markdown || !markdown.trim()) {
    return { type: "doc", content: [{ type: "paragraph" }] };
  }

  // Heading lines often appear without a leading or trailing blank line in
  // agent-authored markdown. Force a paragraph break both BEFORE and AFTER
  // every ATX heading so block-splitting puts each heading on its own block.
  const normalized = markdown
    .replace(/(?<!\n\n)(\n)(#{1,6}[ \t]+)/g, "\n\n$2")
    .replace(/(^|\n\n)(#{1,6}[ \t]+[^\n]+)\n(?!\n)/g, "$1$2\n\n");
  const blocks = normalized.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  const nodes: JSONNode[] = blocks.map((block) => {
    const headingMatch = block.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      return {
        type: "heading",
        attrs: { level: headingMatch[1].length },
        content: parseInlineMarkdown(headingMatch[2]),
      };
    }

    const tableNode = parseTableBlock(block);
    if (tableNode) return tableNode;

    const listNode = parseListBlock(block);
    if (listNode) return listNode;

    return {
      type: "paragraph",
      content: parseInlineMarkdown(block),
    };
  });
  return { type: "doc", content: nodes };
}

// --- Lists ---

const BULLET_RE = /^([-*+])\s+(.*)$/;
const ORDERED_RE = /^\d+\.\s+(.*)$/;

function parseListBlock(block: string): JSONNode | null {
  const lines = block.split("\n");
  const first = lines[0];
  const isBullet = BULLET_RE.test(first);
  const isOrdered = ORDERED_RE.test(first);
  if (!isBullet && !isOrdered) return null;

  const items: JSONNode[] = [];
  for (const line of lines) {
    const m = isBullet ? line.match(BULLET_RE) : line.match(ORDERED_RE);
    if (!m) {
      // Not a list line — fold into the previous item's text if one exists.
      if (items.length > 0) {
        const last = items[items.length - 1];
        const para = last.content?.[0];
        if (para && para.type === "paragraph") {
          para.content = [
            ...(para.content || []),
            { type: "text", text: " " + line.trim() },
          ];
        }
      }
      continue;
    }
    const body = (isBullet ? m[2] : m[1]).trim();
    // Skip bullets with no content — they'd become empty list items that
    // crash the prosemirror renderer.
    if (!body) continue;
    items.push({
      type: "listItem",
      content: [
        {
          type: "paragraph",
          content: parseInlineMarkdown(body),
        },
      ],
    });
  }
  if (items.length === 0) return null;
  return {
    type: isBullet ? "bulletList" : "orderedList",
    content: items,
  };
}

// --- Tables (GitHub-flavored pipe tables) ---

const TABLE_SEPARATOR_RE = /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/;

function splitPipeRow(line: string): string[] {
  // Trim leading/trailing pipe and split on unescaped |.
  const trimmed = line.replace(/^\s*\|/, "").replace(/\|\s*$/, "");
  return trimmed.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
}

function parseTableBlock(block: string): JSONNode | null {
  const lines = block.split("\n");
  if (lines.length < 2) return null;
  if (!lines[0].includes("|")) return null;
  if (!TABLE_SEPARATOR_RE.test(lines[1].trim())) return null;

  const headerCells = splitPipeRow(lines[0]);
  const bodyLines = lines.slice(2);

  const headerRow: JSONNode = {
    type: "tableRow",
    content: headerCells.map((cell) => ({
      type: "tableHeader",
      content: [{ type: "paragraph", content: parseInlineMarkdown(cell) }],
    })),
  };

  const bodyRows: JSONNode[] = bodyLines
    .filter((l) => l.trim())
    .map((line) => {
      const cells = splitPipeRow(line);
      // Normalise cell count to header width.
      while (cells.length < headerCells.length) cells.push("");
      cells.length = headerCells.length;
      return {
        type: "tableRow",
        content: cells.map((cell) => ({
          type: "tableCell",
          content: [{ type: "paragraph", content: parseInlineMarkdown(cell) }],
        })),
      };
    });

  return { type: "table", content: [headerRow, ...bodyRows] };
}

export function serializeMarkdown(doc: JSONNode | null | undefined, fallback: string): string {
  if (!doc || !doc.content) return fallback;
  return doc.content.map((node) => renderNode(node, 0)).join("").trim() || fallback;
}

function renderNode(node: JSONNode, depth: number): string {
  const children = (node.content || []).map((child) => renderNode(child, depth + 1)).join("");
  switch (node.type) {
    case "paragraph":
      return `${children}\n\n`;
    case "heading": {
      const level = Number(node.attrs?.level || 1);
      return `${"#".repeat(Math.min(Math.max(level, 1), 6))} ${children.trim()}\n\n`;
    }
    case "bulletList":
      return `${(node.content || []).map((child) => renderNode(child, depth)).join("")}\n`;
    case "orderedList":
      return `${(node.content || []).map((child, index) => renderListItem(child, depth, index + 1)).join("")}\n`;
    case "listItem":
      return renderListItem(node, depth, null);
    case "blockquote":
      return `${children.trim().split("\n").map((line) => `> ${line}`).join("\n")}\n\n`;
    case "hardBreak":
      return "\n";
    case "image": {
      const src = String(node.attrs?.src || "");
      const alt = String(node.attrs?.alt || "");
      const title = node.attrs?.title ? String(node.attrs.title) : "";
      return title ? `[![${alt}](${src})](${title})` : `![${alt}](${src})`;
    }
    case "table":
      return renderTable(node);
    case "text":
      return applyMarks(node.text || "", node.marks || []);
    default:
      return children;
  }
}

function renderTable(node: JSONNode): string {
  const rows = node.content || [];
  if (rows.length === 0) return "";
  // Each row has tableHeader/tableCell children, each of which contains a
  // paragraph whose text is what we want to serialize.
  const cellsFor = (row: JSONNode): string[] =>
    (row.content || []).map((cell) => {
      const para = (cell.content || [])[0];
      const inline = (para?.content || [])
        .map((child) => renderNode(child, 0))
        .join("")
        .trim();
      return inline.replace(/\|/g, "\\|");
    });

  const headerCells = cellsFor(rows[0]);
  const colCount = headerCells.length;
  const separator = new Array(colCount).fill("---");
  const bodyRows = rows.slice(1).map(cellsFor);
  const toLine = (cells: string[]) => `| ${cells.join(" | ")} |`;
  return [
    toLine(headerCells),
    toLine(separator),
    ...bodyRows.map(toLine),
  ].join("\n") + "\n\n";
}

function renderListItem(node: JSONNode, depth: number, index: number | null): string {
  const prefix = index === null ? `${"  ".repeat(depth)}- ` : `${"  ".repeat(depth)}${index}. `;
  const text = (node.content || []).map((child) => renderNode(child, depth + 1)).join("").trimEnd();
  const lines = text.split("\n");
  return `${prefix}${lines[0] || ""}${lines.slice(1).map((line) => `\n${"  ".repeat(depth + 1)}${line}`).join("")}\n`;
}

function applyMarks(text: string, marks: Array<{ type: string; attrs?: Record<string, string> }>): string {
  return marks.reduce((value, mark) => {
    switch (mark.type) {
      case "bold":
        return `**${value}**`;
      case "italic":
        return `*${value}*`;
      case "underline":
        return `<u>${value}</u>`;
      case "subscript":
        return `<sub>${value}</sub>`;
      case "superscript":
        return `<sup>${value}</sup>`;
      case "link":
        return `[${value}](${mark.attrs?.href || ""})`;
      case "code":
        return `\`${value}\``;
      default:
        return value;
    }
  }, text);
}
