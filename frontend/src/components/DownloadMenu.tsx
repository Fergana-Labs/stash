"use client";

import { useEffect, useRef, useState } from "react";
import { useEscapeKey } from "../hooks/useEscapeKey";

export interface DownloadOption {
  label: string;
  onSelect: () => void;
  // Destructive options render below a divider in red so a misplaced
  // click on "Delete" doesn't land inside the routine download formats.
  destructive?: boolean;
}

export default function DownloadMenu({ options }: { options: DownloadOption[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  const safe = options.filter((o) => !o.destructive);
  const destructive = options.filter((o) => o.destructive);

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex h-7 w-7 cursor-pointer items-center justify-center rounded-md border border-border bg-base text-muted-foreground hover:bg-raised hover:text-foreground"
        aria-label="More actions"
        title="More actions"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <circle cx="5" cy="12" r="1.7" />
          <circle cx="12" cy="12" r="1.7" />
          <circle cx="19" cy="12" r="1.7" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-52 overflow-hidden rounded-md border border-border bg-surface py-1 text-[12.5px] shadow-lg">
          {safe.length > 0 && (
            <div className="px-3 pb-0.5 pt-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Download as</div>
          )}
          {safe.map((o) => (
            <button
              key={o.label}
              onClick={() => {
                setOpen(false);
                o.onSelect();
              }}
              className="flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left text-foreground hover:bg-raised"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-muted-foreground" aria-hidden>
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" x2="12" y1="15" y2="3" />
              </svg>
              {o.label}
            </button>
          ))}
          {destructive.length > 0 && safe.length > 0 && (
            <div className="my-1 border-t border-border" />
          )}
          {destructive.map((o) => (
            <button
              key={o.label}
              onClick={() => {
                setOpen(false);
                o.onSelect();
              }}
              className="block w-full cursor-pointer px-3 py-1.5 text-left text-red-600 hover:bg-red-500/10"
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function downloadBlob(content: BlobPart | BlobPart[], mimeType: string, filename: string) {
  const parts = Array.isArray(content) ? content : [content];
  const blob = new Blob(parts, { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function downloadUrl(url: string, filename: string) {
  const response = await fetch(url);
  if (!response.ok) throw new Error("Download failed");
  const blob = await response.blob();
  downloadBlob(blob, blob.type || "application/octet-stream", filename);
}

export interface PdfBlock {
  text: string;
  level?: 1 | 2 | 3;
  kind?: "paragraph" | "list" | "table" | "meta";
}

export function downloadRenderedPdf({
  title,
  subtitle,
  blocks,
  filename,
}: {
  title: string;
  subtitle?: string;
  blocks: PdfBlock[];
  filename: string;
}) {
  const pdf = buildSimplePdf([
    { text: title || "Untitled", level: 1 },
    ...(subtitle ? [{ text: subtitle, kind: "meta" as const }] : []),
    ...blocks,
  ]);
  downloadBlob(pdf, "application/pdf", filename);
}

export function markdownToPdfBlocks(markdown: string): PdfBlock[] {
  const blocks: PdfBlock[] = [];
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  let paragraph: string[] = [];

  function flushParagraph() {
    const text = paragraph.join(" ").trim();
    if (text) blocks.push({ text: plainMarkdown(text), kind: "paragraph" });
    paragraph = [];
  }

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      continue;
    }

    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      blocks.push({
        text: plainMarkdown(heading[2]),
        level: heading[1].length as 1 | 2 | 3,
      });
      continue;
    }

    const unordered = trimmed.match(/^[-*+]\s+(.+)$/);
    const ordered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      blocks.push({ text: `- ${plainMarkdown((unordered || ordered)?.[1] || "")}`, kind: "list" });
      continue;
    }

    if (trimmed.includes("|")) {
      flushParagraph();
      blocks.push({
        text: plainMarkdown(trimmed.replace(/^\|/, "").replace(/\|$/, "").replace(/\|/g, " | ")),
        kind: "table",
      });
      continue;
    }

    paragraph.push(trimmed);
  }

  flushParagraph();
  return blocks;
}

export function htmlToPdfBlocks(html: string): PdfBlock[] {
  const document = new DOMParser().parseFromString(html, "text/html");
  const root = document.body?.childNodes.length ? document.body : document.documentElement;
  const blocks: PdfBlock[] = [];

  function walk(node: Node) {
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const element = node as HTMLElement;
    const tag = element.tagName.toLowerCase();
    const text = element.innerText?.replace(/\s+/g, " ").trim();

    if (tag === "h1" || tag === "h2" || tag === "h3") {
      if (text) blocks.push({ text, level: Number(tag.slice(1)) as 1 | 2 | 3 });
      return;
    }

    if (tag === "p" || tag === "li" || tag === "blockquote") {
      if (text) blocks.push({ text: tag === "li" ? `- ${text}` : text, kind: tag === "li" ? "list" : "paragraph" });
      return;
    }

    if (tag === "tr") {
      const cells = Array.from(element.querySelectorAll("th,td"))
        .map((cell) => cell.textContent?.replace(/\s+/g, " ").trim())
        .filter(Boolean);
      if (cells.length) blocks.push({ text: cells.join(" | "), kind: "table" });
      return;
    }

    if (tag === "img") {
      const alt = element.getAttribute("alt") || element.getAttribute("src") || "Image";
      blocks.push({ text: `[Image: ${alt}]`, kind: "paragraph" });
      return;
    }

    element.childNodes.forEach(walk);
  }

  root.childNodes.forEach(walk);
  return blocks;
}

function plainMarkdown(value: string): string {
  return value
    .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_match, alt) => `[Image: ${alt || "image"}]`)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1 ($2)")
    .replace(/[*_`~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function buildSimplePdf(blocks: PdfBlock[]): string {
  const pageWidth = 612;
  const pageHeight = 792;
  const margin = 54;
  const bottom = 54;
  const maxWidth = pageWidth - margin * 2;
  const pages: string[][] = [[]];
  let y = pageHeight - margin;

  function addLine(text: string, fontSize: number, bold: boolean, gapAfter = 4) {
    if (y < bottom + fontSize) {
      pages.push([]);
      y = pageHeight - margin;
    }
    const font = bold ? "F2" : "F1";
    pages[pages.length - 1].push(
      `BT /${font} ${fontSize} Tf ${margin.toFixed(2)} ${y.toFixed(2)} Td (${escapePdfText(text)}) Tj ET`
    );
    y -= fontSize + gapAfter;
  }

  for (const block of blocks) {
    const fontSize = block.level === 1 ? 22 : block.level === 2 ? 17 : block.level === 3 ? 14 : block.kind === "meta" ? 9 : 11;
    const bold = !!block.level || block.kind === "table";
    const gap = block.level ? 8 : block.kind === "meta" ? 12 : 5;
    const text = normalizePdfText(block.text);
    if (!text) continue;
    for (const line of wrapPdfLine(text, maxWidth, fontSize)) {
      addLine(line, fontSize, bold, gap);
    }
    if (!block.level) y -= 3;
  }

  const objects: string[] = [];
  const addObject = (body: string) => {
    objects.push(body);
    return objects.length;
  };

  const fontRegular = addObject("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  const fontBold = addObject("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>");
  const pageRefs: number[] = [];

  for (const lines of pages) {
    const stream = lines.join("\n");
    const contentRef = addObject(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
    const pageRef = addObject(
      `<< /Type /Page /Parent 0 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Resources << /Font << /F1 ${fontRegular} 0 R /F2 ${fontBold} 0 R >> >> /Contents ${contentRef} 0 R >>`
    );
    pageRefs.push(pageRef);
  }

  const pagesRef = addObject(`<< /Type /Pages /Kids [${pageRefs.map((ref) => `${ref} 0 R`).join(" ")}] /Count ${pageRefs.length} >>`);
  const catalogRef = addObject(`<< /Type /Catalog /Pages ${pagesRef} 0 R >>`);

  for (const ref of pageRefs) {
    objects[ref - 1] = objects[ref - 1].replace("/Parent 0 0 R", `/Parent ${pagesRef} 0 R`);
  }

  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((body, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (let i = 1; i < offsets.length; i += 1) {
    pdf += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root ${catalogRef} 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return pdf;
}

function wrapPdfLine(text: string, maxWidth: number, fontSize: number): string[] {
  const maxChars = Math.max(12, Math.floor(maxWidth / (fontSize * 0.52)));
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let current = "";

  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length <= maxChars) {
      current = next;
      continue;
    }
    if (current) lines.push(current);
    current = word.length > maxChars ? word.slice(0, maxChars) : word;
  }
  if (current) lines.push(current);
  return lines;
}

function normalizePdfText(text: string): string {
  return text.normalize("NFKD").replace(/[^\x20-\x7E]/g, "").trim();
}

function escapePdfText(text: string): string {
  return text.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}
