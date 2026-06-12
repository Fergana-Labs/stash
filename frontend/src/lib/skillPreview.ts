export type SkillItemType = "folder" | "page" | "table" | "file";

// Loosely-typed contents payload: OG/social previews must never crash on a
// partial or older-shaped response, so every field read goes through the
// defensive value helpers at the bottom.
export type SkillPreviewContents = {
  subfolders: Record<string, unknown>[];
  pages: Record<string, unknown>[];
  files: Record<string, unknown>[];
  tables: Record<string, unknown>[];
};

export type SkillPreviewData = {
  skill: {
    id: string;
    workspace_id: string;
    slug: string;
    title: string;
    description: string;
    owner_name?: string;
    owner_display_name?: string | null;
    cover_image_url?: string | null;
    icon_url?: string | null;
    updated_at?: string;
  };
  workspace_name: string;
  folder_name?: string;
  contents: SkillPreviewContents;
  can_write?: boolean;
};

export type SkillPreviewItem = {
  type: SkillItemType;
  item: Record<string, unknown>;
};

export type PreviewLine = {
  label: string;
  meta: string;
  excerpt: string;
};

export type PreviewCard = {
  kind: "skill" | SkillItemType;
  title: string;
  description: string;
  workspaceName: string;
  skillTitle: string;
  authorName: string;
  updatedAt: string | null;
  coverImageUrl: string | null;
  iconUrl: string | null;
  contentBadge: string;
  bodyTitle: string;
  bodyText: string;
  stats: string[];
  lines: PreviewLine[];
};

const ITEM_TYPES = new Set(["folder", "page", "table", "file"]);

export function isSkillItemType(value: string | null): value is SkillItemType {
  return !!value && ITEM_TYPES.has(value);
}

export function findSkillItem(
  contents: SkillPreviewContents,
  type: SkillItemType,
  id: string,
): SkillPreviewItem | null {
  const list =
    type === "page"
      ? contents.pages
      : type === "file"
        ? contents.files
        : type === "table"
          ? contents.tables
          : contents.subfolders;
  const item = (list ?? []).find((entry) => stringValue(entry.id) === id);
  return item ? { type, item } : null;
}

export function skillMetadataTitle(data: SkillPreviewData): string {
  return `${data.skill.title} - Skill`;
}

export function skillMetadataDescription(data: SkillPreviewData): string {
  const description = cleanText(data.skill.description);
  if (description) return truncateText(description, 220);

  const counts = contentsTypeCounts(data.contents);
  const total =
    (data.contents.pages?.length ?? 0) +
    (data.contents.files?.length ?? 0) +
    (data.contents.tables?.length ?? 0);
  const plural = total === 1 ? "" : "s";
  const countDetail = counts.length ? `: ${counts.join(", ")}` : "";
  return `A Skill with ${total} file${plural}${countDetail} from ${data.workspace_name}.`;
}

export function itemMetadataTitle(
  data: SkillPreviewData,
  item: SkillPreviewItem,
): string {
  const label = itemName(item) || formatItemType(item.type);
  return `${label} - ${data.skill.title} - Skill`;
}

export function itemMetadataDescription(
  data: SkillPreviewData,
  item: SkillPreviewItem,
): string {
  const summary = itemSummary(item);
  const prefix = `${formatItemType(item.type)} in ${data.skill.title}`;
  return truncateText(summary ? `${prefix}: ${summary}` : prefix, 220);
}

export function skillOgImagePath(
  slug: string,
  itemType?: SkillItemType,
  itemId?: string,
): string {
  const params = new URLSearchParams({ slug });
  if (itemType && itemId) {
    params.set("type", itemType);
    params.set("id", itemId);
  }
  return `/api/og/skill?${params.toString()}`;
}

export function buildSkillPreviewCard(data: SkillPreviewData): PreviewCard {
  const description = skillMetadataDescription(data);
  const stats = [
    data.workspace_name,
    ...contentsTypeCounts(data.contents).slice(0, 3),
  ].filter(Boolean);
  const lines = contentsPreviewLines(data.contents);

  return {
    kind: "skill",
    title: data.skill.title,
    description,
    workspaceName: data.workspace_name,
    skillTitle: data.skill.title,
    authorName: skillAuthorName(data),
    updatedAt: data.skill.updated_at ?? null,
    coverImageUrl: data.skill.cover_image_url ?? null,
    iconUrl: data.skill.icon_url ?? null,
    contentBadge: "SKILL",
    bodyTitle: lines.length > 0 ? "Contents" : "Nothing here yet",
    bodyText: description,
    stats,
    lines,
  };
}

export function buildItemPreviewCard(
  data: SkillPreviewData,
  item: SkillPreviewItem,
): PreviewCard {
  const label = itemName(item) || formatItemType(item.type);
  const body = itemPreviewBody(item, label);
  return {
    kind: item.type,
    title: label,
    description: itemMetadataDescription(data, item),
    workspaceName: data.workspace_name,
    skillTitle: data.skill.title,
    authorName: skillAuthorName(data),
    updatedAt: itemUpdatedAt(item) ?? data.skill.updated_at ?? null,
    coverImageUrl: data.skill.cover_image_url ?? null,
    iconUrl: data.skill.icon_url ?? null,
    contentBadge: itemContentBadge(item),
    bodyTitle: body.title,
    bodyText: body.text,
    stats: [data.workspace_name, data.skill.title, formatItemType(item.type)],
    lines: itemPreviewLines(item, label),
  };
}

export function formatItemType(type: SkillItemType): string {
  return type[0].toUpperCase() + type.slice(1);
}

export function itemSummary(item: SkillPreviewItem): string {
  if (item.type === "page") {
    return truncateText(pageText(item.item) || "Page", 220);
  }

  if (item.type === "table") {
    const description = cleanText(stringValue(item.item.description));
    if (description) return truncateText(description, 180);
    const columns = arrayValue(item.item.columns);
    const rows = arrayValue(item.item.rows);
    return `${columns.length} column${columns.length === 1 ? "" : "s"}, ${rows.length} row${
      rows.length === 1 ? "" : "s"
    }`;
  }

  if (item.type === "file") {
    const contentType = stringValue(item.item.content_type) || "file";
    const size = numberValue(item.item.size_bytes);
    return size == null ? contentType : `${contentType}, ${formatBytes(size)}`;
  }

  return itemName(item);
}

function itemName(item: SkillPreviewItem): string {
  return stringValue(item.item.name);
}

function contentsPreviewLines(contents: SkillPreviewContents): PreviewLine[] {
  const pageLines = (contents.pages ?? []).slice(0, 4).map((page) => ({
    label: stringValue(page.name) || "Page",
    meta: "Page",
    excerpt: truncateText(pageText(page) || "Page", 150),
  }));
  const fileLines = (contents.files ?? [])
    .slice(0, Math.max(0, 4 - pageLines.length))
    .map((file) => ({
      label: stringValue(file.name) || "File",
      meta: stringValue(file.content_type) || "File",
      excerpt: fileSummary(file),
    }));
  return [...pageLines, ...fileLines];
}

function itemPreviewLines(item: SkillPreviewItem, label: string): PreviewLine[] {
  if (item.type === "page") {
    return textLines(pageText(item.item), label);
  }

  if (item.type === "table") {
    const columns = arrayValue(item.item.columns).map(objectValue);
    const rows = arrayValue(item.item.rows).map(objectValue);
    const columnNames = columns
      .map((column) => stringValue(column.name))
      .filter(Boolean)
      .slice(0, 6)
      .join(", ");
    return [
      {
        label: "Columns",
        meta: `${columns.length} total`,
        excerpt: columnNames || "No columns",
      },
      {
        label: "Rows",
        meta: `${rows.length} visible`,
        excerpt: firstTableRow(columns, rows),
      },
    ];
  }

  return [
    {
      label,
      meta: formatItemType(item.type),
      excerpt: itemSummary(item),
    },
  ];
}

function itemPreviewBody(
  item: SkillPreviewItem,
  fallbackTitle: string,
): { title: string; text: string } {
  if (item.type === "page") {
    return pagePreviewBody(item.item, fallbackTitle);
  }

  if (item.type === "table") {
    const columns = arrayValue(item.item.columns).map(objectValue);
    const rows = arrayValue(item.item.rows).map(objectValue);
    return {
      title: fallbackTitle,
      text: `${columns.length} columns, ${rows.length} rows. ${firstTableRow(columns, rows)}`,
    };
  }

  return {
    title: fallbackTitle,
    text: itemSummary(item),
  };
}

function pagePreviewBody(
  page: Record<string, unknown>,
  fallbackTitle: string,
): { title: string; text: string } {
  const markdown = stringValue(page.content_markdown).trim();
  if (!markdown) {
    return htmlPreviewBody(stringValue(page.content_html), fallbackTitle);
  }

  const rawLines = markdown
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const headingIndex = rawLines.findIndex((line) => /^#{1,6}\s+/.test(line));
  if (headingIndex >= 0) {
    const title = stripMarkdownLine(rawLines[headingIndex]);
    const text = rawLines
      .slice(headingIndex + 1)
      .map(stripMarkdownLine)
      .filter(Boolean)
      .join(" ");
    return {
      title: title || fallbackTitle,
      text: truncateText(text || pageText(page), 260),
    };
  }

  return {
    title: fallbackTitle,
    text: truncateText(markdownPreviewText(markdown), 260),
  };
}

function htmlPreviewBody(
  html: string,
  fallbackTitle: string,
): { title: string; text: string } {
  const lines = htmlTextLines(html);
  const firstLine = lines[0] ?? "";
  const firstLineLooksLikeTitle = firstLine.length > 0 && firstLine.length <= 140;
  const title = firstLineLooksLikeTitle ? firstLine : fallbackTitle;
  const textLines = firstLineLooksLikeTitle ? lines.slice(1) : lines;
  return {
    title,
    text: truncateText(textLines.join(" "), 260),
  };
}

function itemContentBadge(item: SkillPreviewItem): string {
  if (item.type === "page") {
    const contentType = stringValue(item.item.content_type);
    return contentType.toLowerCase() === "html" ? "HTML" : "PAGE";
  }
  if (item.type === "file") return fileContentBadge(item.item);
  return formatItemType(item.type).toUpperCase();
}

function fileContentBadge(file: Record<string, unknown>): string {
  const contentType = stringValue(file.content_type).toLowerCase();
  if (contentType.includes("pdf")) return "PDF";
  if (contentType.startsWith("image/")) return "IMAGE";
  if (contentType.includes("html")) return "HTML";
  if (contentType.startsWith("text/")) return "TEXT";
  return "FILE";
}

function itemUpdatedAt(item: SkillPreviewItem): string | null {
  if (item.type === "page") return stringValue(item.item.updated_at) || null;
  if (item.type === "file") return stringValue(item.item.created_at) || null;
  return null;
}

function firstTableRow(columns: Record<string, unknown>[], rows: Record<string, unknown>[]): string {
  const firstRow = objectValue(rows[0]?.data);
  if (!firstRow || Object.keys(firstRow).length === 0) return "No rows";
  const values = columns
    .slice(0, 4)
    .map((column) => {
      const name = stringValue(column.name);
      return name ? stringValue(firstRow[name]) : "";
    })
    .filter(Boolean);
  return truncateText(values.join(", ") || "No populated cells", 150);
}

function textLines(text: string, fallbackLabel: string): PreviewLine[] {
  const sentences = cleanText(text)
    .split(/(?<=[.!?])\s+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 3);

  if (sentences.length === 0) {
    return [{ label: fallbackLabel, meta: "Page", excerpt: "No preview text available" }];
  }

  return sentences.map((sentence, index) => ({
    label: index === 0 ? fallbackLabel : `Excerpt ${index + 1}`,
    meta: "Page",
    excerpt: truncateText(sentence, 150),
  }));
}

function fileSummary(file: Record<string, unknown>): string {
  const contentType = stringValue(file.content_type) || "file";
  const size = numberValue(file.size_bytes);
  return size == null ? contentType : `${contentType} - ${formatBytes(size)}`;
}

function pageText(page: Record<string, unknown>): string {
  const markdown = stringValue(page.content_markdown);
  if (markdown.trim()) return markdownPreviewText(markdown);
  return stripHtml(stringValue(page.content_html));
}

function contentsTypeCounts(contents: SkillPreviewContents): string[] {
  const counts: [string, number][] = [
    ["page", contents.pages?.length ?? 0],
    ["file", contents.files?.length ?? 0],
    ["table", contents.tables?.length ?? 0],
  ];
  return counts
    .filter(([, count]) => count > 0)
    .map(([label, count]) => `${count} ${label}${count === 1 ? "" : "s"}`);
}

function stripHtml(html: string): string {
  return cleanText(htmlTextLines(html).join(" "));
}

function htmlTextLines(html: string): string[] {
  return html
    .replace(/<head[\s\S]*?<\/head>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|h[1-6]|tr)>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .split(/\n+/)
    .map(cleanText)
    .filter(Boolean);
}

function markdownPreviewText(markdown: string): string {
  return cleanText(
    markdown
      .replace(/```[\s\S]*?```/g, " ")
      .split(/\n+/)
      .map(stripMarkdownLine)
      .join(" "),
  );
}

function stripMarkdownLine(line: string): string {
  return cleanText(
    line
      .replace(/^#{1,6}\s+/, "")
      .replace(/^[-*]\s+/, "")
      .replace(/^>\s+/, "")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1"),
  );
}

function cleanText(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function skillAuthorName(data: SkillPreviewData): string {
  return data.skill.owner_display_name || data.skill.owner_name || "";
}

function truncateText(text: string, limit: number): string {
  const clean = cleanText(text);
  if (clean.length <= limit) return clean;
  return `${clean.slice(0, limit - 3).trimEnd()}...`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function objectValue(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
}

function stringValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
