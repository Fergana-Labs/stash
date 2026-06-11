export type SkillItemType = "folder" | "page" | "table" | "file" | "session";

export type SkillPreviewItem = {
  object_type: SkillItemType;
  object_id: string;
  position: number;
  label: string;
  inline: Record<string, unknown>;
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
  items: SkillPreviewItem[];
  can_write?: boolean;
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

const ITEM_TYPES = new Set(["folder", "page", "table", "file", "session"]);

export function isSkillItemType(value: string | null): value is SkillItemType {
  return !!value && ITEM_TYPES.has(value);
}

export function findSkillItem(
  items: SkillPreviewItem[],
  objectType: SkillItemType,
  objectId: string,
): SkillPreviewItem | null {
  return (
    items.find((item) => {
      if (item.object_type !== objectType) return false;
      if (String(item.object_id) === objectId) return true;
      if (objectType !== "session") return false;
      const session = objectValue(item.inline.session);
      return stringValue(session.session_id) === objectId;
    }) ?? null
  );
}

export function skillMetadataTitle(data: SkillPreviewData): string {
  return `${data.skill.title} - Skill`;
}

export function skillMetadataDescription(data: SkillPreviewData): string {
  const description = cleanText(data.skill.description);
  if (description) return truncateText(description, 220);

  const itemCount = data.items.length;
  const plural = itemCount === 1 ? "" : "s";
  const counts = itemTypeCounts(data.items).join(", ");
  const countDetail = counts ? `: ${counts}` : "";
  return `A Skill with ${itemCount} item${plural}${countDetail} from ${data.workspace_name}.`;
}

export function itemMetadataTitle(
  data: SkillPreviewData,
  item: SkillPreviewItem,
): string {
  const label = item.label || formatItemType(item.object_type);
  return `${label} - ${data.skill.title} - Skill`;
}

export function itemMetadataDescription(
  data: SkillPreviewData,
  item: SkillPreviewItem,
): string {
  const summary = itemSummary(item);
  const prefix = `${formatItemType(item.object_type)} in ${data.skill.title}`;
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
    ...itemTypeCounts(data.items).slice(0, 3),
  ].filter(Boolean);
  const lines = data.items.slice(0, 4).map(itemPreviewLine);

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
    bodyTitle: data.items.length > 0 ? "Contents" : "No items yet",
    bodyText: description,
    stats,
    lines,
  };
}

export function buildItemPreviewCard(
  data: SkillPreviewData,
  item: SkillPreviewItem,
): PreviewCard {
  const label = item.label || formatItemType(item.object_type);
  const body = itemPreviewBody(item, label);
  return {
    kind: item.object_type,
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
    stats: [data.workspace_name, data.skill.title, formatItemType(item.object_type)],
    lines: itemPreviewLines(item),
  };
}

export function formatItemType(type: SkillItemType): string {
  if (type === "session") return "Session";
  return type[0].toUpperCase() + type.slice(1);
}

export function itemPreviewLine(item: SkillPreviewItem): PreviewLine {
  return {
    label: item.label || formatItemType(item.object_type),
    meta: itemMeta(item),
    excerpt: itemSummary(item),
  };
}

export function itemSummary(item: SkillPreviewItem): string {
  const inline = item.inline ?? {};

  if (item.object_type === "folder") {
    const pages = arrayValue(inline.pages);
    const files = arrayValue(inline.files);
    const firstPage = objectValue(pages[0]);
    const firstPageText = pageText(firstPage);
    if (firstPageText) return truncateText(firstPageText, 180);
    return `${pages.length} page${pages.length === 1 ? "" : "s"}, ${files.length} file${
      files.length === 1 ? "" : "s"
    }`;
  }

  if (item.object_type === "page") {
    const page = objectValue(inline.page);
    return truncateText(pageText(page) || "Page", 220);
  }

  if (item.object_type === "table") {
    const description = cleanText(stringValue(inline.description));
    if (description) return truncateText(description, 180);
    const columns = arrayValue(inline.columns);
    const rows = arrayValue(inline.rows);
    return `${columns.length} column${columns.length === 1 ? "" : "s"}, ${rows.length} row${
      rows.length === 1 ? "" : "s"
    }`;
  }

  if (item.object_type === "file") {
    const contentType = stringValue(inline.content_type) || "file";
    const size = numberValue(inline.size_bytes);
    return size == null ? contentType : `${contentType}, ${formatBytes(size)}`;
  }

  if (item.object_type === "session") {
    const session = objectValue(inline.session);
    const events = arrayValue(session.events);
    const firstEvent = events
      .map(objectValue)
      .map((event) => cleanText(stringValue(event.content)))
      .find(Boolean);
    if (firstEvent) return truncateText(firstEvent, 180);
    const agent = stringValue(session.agent_name) || "Agent";
    return `${agent} session, ${events.length} event${events.length === 1 ? "" : "s"}`;
  }

  return item.label;
}

function itemPreviewLines(item: SkillPreviewItem): PreviewLine[] {
  const inline = item.inline ?? {};

  if (item.object_type === "folder") {
    const pages = arrayValue(inline.pages);
    const files = arrayValue(inline.files);
    const pageLines = pages.slice(0, 3).map((page) => {
      const pageObject = objectValue(page);
      return {
        label: stringValue(pageObject.name) || "Page",
        meta: "Page",
        excerpt: truncateText(pageText(pageObject) || "Page", 150),
      };
    });
    const fileLines = files.slice(0, Math.max(0, 3 - pageLines.length)).map((file) => {
      const fileObject = objectValue(file);
      return {
        label: stringValue(fileObject.name) || "File",
        meta: stringValue(fileObject.content_type) || "File",
        excerpt: fileSummary(fileObject),
      };
    });
    return [...pageLines, ...fileLines];
  }

  if (item.object_type === "page") {
    const page = objectValue(inline.page);
    return textLines(pageText(page), "Excerpt");
  }

  if (item.object_type === "table") {
    const columns = arrayValue(inline.columns).map(objectValue);
    const rows = arrayValue(inline.rows).map(objectValue);
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

  if (item.object_type === "file") {
    return [
      {
        label: item.label || stringValue(inline.name) || "File",
        meta: stringValue(inline.content_type) || "File",
        excerpt: fileSummary(inline),
      },
    ];
  }

  if (item.object_type === "session") {
    const session = objectValue(inline.session);
    const events = arrayValue(session.events).map(objectValue);
    const eventLines = events
      .map((event) => ({
        label: stringValue(event.agent_name) || stringValue(session.agent_name) || "Agent",
        meta: stringValue(event.event_type) || "Event",
        excerpt: truncateText(cleanText(stringValue(event.content)), 150),
      }))
      .filter((line) => line.excerpt)
      .slice(0, 3);
    if (eventLines.length > 0) return eventLines;
  }

  return [itemPreviewLine(item)];
}

function itemPreviewBody(
  item: SkillPreviewItem,
  fallbackTitle: string,
): { title: string; text: string } {
  const inline = item.inline ?? {};

  if (item.object_type === "page") {
    const page = objectValue(inline.page);
    return pagePreviewBody(page, fallbackTitle);
  }

  if (item.object_type === "session") {
    const session = objectValue(inline.session);
    const events = arrayValue(session.events).map(objectValue);
    const firstEvent = events
      .map((event) => cleanText(stringValue(event.content)))
      .find(Boolean);
    return {
      title: fallbackTitle,
      text: firstEvent ? truncateText(firstEvent, 260) : itemSummary(item),
    };
  }

  if (item.object_type === "table") {
    const columns = arrayValue(inline.columns).map(objectValue);
    const rows = arrayValue(inline.rows).map(objectValue);
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
  const inline = item.inline ?? {};
  if (item.object_type === "page") {
    const page = objectValue(inline.page);
    const contentType = stringValue(page.content_type);
    return contentType.toLowerCase() === "html" ? "HTML" : "PAGE";
  }
  if (item.object_type === "file") return fileContentBadge(inline);
  return formatItemType(item.object_type).toUpperCase();
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
  const inline = item.inline ?? {};
  if (item.object_type === "page") {
    return stringValue(objectValue(inline.page).updated_at) || null;
  }
  if (item.object_type === "file") return stringValue(inline.created_at) || null;
  if (item.object_type === "session") {
    const session = objectValue(inline.session);
    return stringValue(session.finished_at) || stringValue(session.started_at) || null;
  }
  return null;
}

function itemMeta(item: SkillPreviewItem): string {
  const inline = item.inline ?? {};
  if (item.object_type === "folder") {
    const pages = arrayValue(inline.pages).length;
    const files = arrayValue(inline.files).length;
    return `${pages} page${pages === 1 ? "" : "s"} - ${files} file${files === 1 ? "" : "s"}`;
  }
  if (item.object_type === "table") {
    return `${arrayValue(inline.columns).length} columns - ${arrayValue(inline.rows).length} rows`;
  }
  if (item.object_type === "file") return stringValue(inline.content_type) || "File";
  if (item.object_type === "session") {
    const session = objectValue(inline.session);
    return `${stringValue(session.agent_name) || "Agent"} session`;
  }
  return formatItemType(item.object_type);
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

function itemTypeCounts(items: SkillPreviewItem[]): string[] {
  const counts = new Map<SkillItemType, number>();
  for (const item of items) {
    counts.set(item.object_type, (counts.get(item.object_type) ?? 0) + 1);
  }
  return Array.from(counts.entries()).map(([type, count]) => {
    const label = type === "session" ? "session" : type;
    return `${count} ${label}${count === 1 ? "" : "s"}`;
  });
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
  return Array.isArray(value) ? value : [];
}

function stringValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
