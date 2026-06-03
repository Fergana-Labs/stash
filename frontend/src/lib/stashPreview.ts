export type StashItemType = "folder" | "page" | "table" | "file" | "session";

export type StashPreviewItem = {
  object_type: StashItemType;
  object_id: string;
  position: number;
  label: string;
  inline: Record<string, unknown>;
};

export type StashPreviewData = {
  stash: {
    id: string;
    workspace_id: string;
    slug: string;
    title: string;
    description: string;
    owner_name?: string;
    owner_display_name?: string | null;
    cover_image_url?: string | null;
    icon_url?: string | null;
  };
  workspace_name: string;
  items: StashPreviewItem[];
  can_write?: boolean;
};

export type PreviewLine = {
  label: string;
  meta: string;
  excerpt: string;
};

export type PreviewCard = {
  eyebrow: string;
  title: string;
  description: string;
  stats: string[];
  lines: PreviewLine[];
  accent: {
    primary: string;
    secondary: string;
    wash: string;
  };
};

const ITEM_TYPES = new Set(["folder", "page", "table", "file", "session"]);

const ACCENTS = [
  { primary: "#2563EB", secondary: "#14B8A6", wash: "#DBEAFE" },
  { primary: "#059669", secondary: "#F97316", wash: "#D1FAE5" },
  { primary: "#7C3AED", secondary: "#06B6D4", wash: "#EDE9FE" },
  { primary: "#EA580C", secondary: "#2563EB", wash: "#FFEDD5" },
  { primary: "#0F766E", secondary: "#E11D48", wash: "#CCFBF1" },
];

export function isStashItemType(value: string | null): value is StashItemType {
  return !!value && ITEM_TYPES.has(value);
}

export function findStashItem(
  items: StashPreviewItem[],
  objectType: StashItemType,
  objectId: string,
): StashPreviewItem | null {
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

export function stashMetadataTitle(data: StashPreviewData): string {
  return `${data.stash.title} - Stash`;
}

export function stashMetadataDescription(data: StashPreviewData): string {
  const description = cleanText(data.stash.description);
  if (description) return truncateText(description, 220);

  const itemCount = data.items.length;
  const plural = itemCount === 1 ? "" : "s";
  const counts = itemTypeCounts(data.items).join(", ");
  const countDetail = counts ? `: ${counts}` : "";
  return `A Stash with ${itemCount} item${plural}${countDetail} from ${data.workspace_name}.`;
}

export function itemMetadataTitle(
  data: StashPreviewData,
  item: StashPreviewItem,
): string {
  const label = item.label || formatItemType(item.object_type);
  return `${label} - ${data.stash.title} - Stash`;
}

export function itemMetadataDescription(
  data: StashPreviewData,
  item: StashPreviewItem,
): string {
  const summary = itemSummary(item);
  const prefix = `${formatItemType(item.object_type)} in ${data.stash.title}`;
  return truncateText(summary ? `${prefix}: ${summary}` : prefix, 220);
}

export function stashOgImagePath(
  slug: string,
  itemType?: StashItemType,
  itemId?: string,
): string {
  const params = new URLSearchParams({ slug });
  if (itemType && itemId) {
    params.set("type", itemType);
    params.set("id", itemId);
  }
  return `/api/og/stash?${params.toString()}`;
}

export function buildStashPreviewCard(data: StashPreviewData): PreviewCard {
  const description = stashMetadataDescription(data);
  const stats = [
    data.workspace_name,
    ...itemTypeCounts(data.items).slice(0, 3),
  ].filter(Boolean);

  return {
    eyebrow: "Stash",
    title: data.stash.title,
    description,
    stats,
    lines: data.items.slice(0, 4).map(itemPreviewLine),
    accent: accentFor(data.stash.id || data.stash.slug),
  };
}

export function buildItemPreviewCard(
  data: StashPreviewData,
  item: StashPreviewItem,
): PreviewCard {
  const label = item.label || formatItemType(item.object_type);
  return {
    eyebrow: `${formatItemType(item.object_type)} in ${data.stash.title}`,
    title: label,
    description: itemMetadataDescription(data, item),
    stats: [data.workspace_name, data.stash.title, formatItemType(item.object_type)],
    lines: itemPreviewLines(item),
    accent: accentFor(`${data.stash.id}:${item.object_type}:${item.object_id}`),
  };
}

export function formatItemType(type: StashItemType): string {
  if (type === "session") return "Session";
  return type[0].toUpperCase() + type.slice(1);
}

export function itemPreviewLine(item: StashPreviewItem): PreviewLine {
  return {
    label: item.label || formatItemType(item.object_type),
    meta: itemMeta(item),
    excerpt: itemSummary(item),
  };
}

export function itemSummary(item: StashPreviewItem): string {
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

function itemPreviewLines(item: StashPreviewItem): PreviewLine[] {
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

function itemMeta(item: StashPreviewItem): string {
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
  const markdown = cleanText(stringValue(page.content_markdown));
  if (markdown) return markdown;
  return stripHtml(stringValue(page.content_html));
}

function itemTypeCounts(items: StashPreviewItem[]): string[] {
  const counts = new Map<StashItemType, number>();
  for (const item of items) {
    counts.set(item.object_type, (counts.get(item.object_type) ?? 0) + 1);
  }
  return Array.from(counts.entries()).map(([type, count]) => {
    const label = type === "session" ? "session" : type;
    return `${count} ${label}${count === 1 ? "" : "s"}`;
  });
}

function accentFor(seed: string) {
  let hash = 5381;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 33 + seed.charCodeAt(i)) >>> 0;
  }
  return ACCENTS[hash % ACCENTS.length];
}

function stripHtml(html: string): string {
  return cleanText(
    html
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
      .replace(/&#39;/g, "'"),
  );
}

function cleanText(text: string): string {
  return text.replace(/\s+/g, " ").trim();
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
