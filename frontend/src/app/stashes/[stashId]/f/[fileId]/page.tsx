"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import AppShell from "../../../../../components/AppShell";
import { useBreadcrumbs } from "../../../../../components/BreadcrumbContext";
import { useAuth } from "../../../../../hooks/useAuth";
import { getFile } from "../../../../../lib/api";
import type { FileInfo } from "../../../../../lib/types";

function isCsv(ct: string) {
  return ct?.includes("csv") || ct?.startsWith("text/csv");
}
function isHtml(ct: string) {
  return ct?.includes("html");
}
function isPdf(ct: string) {
  return ct?.includes("pdf");
}
function isImage(ct: string) {
  return ct?.startsWith("image/");
}
function isMarkdown(ct: string, name: string) {
  return ct?.includes("markdown") || name.toLowerCase().endsWith(".md");
}
function isText(ct: string) {
  return ct?.startsWith("text/");
}

export default function FileViewerPage() {
  const params = useParams();
  const router = useRouter();
  const stashId = params.stashId as string;
  const fileId = params.fileId as string;
  const { user, loading, logout } = useAuth();

  const [file, setFile] = useState<FileInfo | null>(null);
  const [textBody, setTextBody] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [csvTab, setCsvTab] = useState<"table" | "chart" | "raw">("table");

  useBreadcrumbs(
    file ? [{ label: file.name }] : [{ label: "File" }],
    `${stashId}/file/${fileId}/${file?.name ?? ""}`
  );

  const load = useCallback(async () => {
    try {
      const f = await getFile(stashId, fileId);
      setFile(f);
      if (f.url && (isText(f.content_type) || isMarkdown(f.content_type, f.name) || isCsv(f.content_type))) {
        const res = await fetch(f.url);
        if (res.ok) setTextBody(await res.text());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load file");
    }
  }, [stashId, fileId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  const csvMode = file && isCsv(file.content_type);

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex flex-1 min-h-0 flex-col overflow-hidden">
        {/* File toolbar */}
        <div className="flex items-center justify-between border-b border-border px-5 py-2.5 text-[13px]">
          <div className="flex items-center gap-2">
            <span className="font-mono font-medium text-foreground">{file?.name}</span>
            {file && (
              <span className="text-muted">
                {file.content_type} · {formatBytes(file.size_bytes)}
              </span>
            )}
            {csvMode && (
              <span className="ml-1 inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] font-medium text-emerald-700 ring-1 ring-emerald-200">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> live
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {csvMode && (
              <div className="flex rounded-md border border-border bg-base p-0.5 text-[12px]">
                {(["table", "chart", "raw"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setCsvTab(t)}
                    className={
                      "rounded px-2.5 py-1 capitalize " +
                      (csvTab === t
                        ? "bg-raised font-medium text-foreground"
                        : "text-muted hover:text-foreground")
                    }
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
            {file?.url && (
              <a
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                download={file.name}
                className="rounded-md p-1.5 text-muted hover:bg-raised"
                title="Download"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
                </svg>
              </a>
            )}
            {csvMode && (
              <button
                className="ml-1 inline-flex items-center gap-1.5 rounded-md bg-[var(--color-brand-50)] px-2.5 py-1.5 text-[12px] font-medium text-[var(--color-brand-700)] ring-1 ring-[var(--color-brand-200)] hover:bg-[var(--color-brand-100)]"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="m12 3 1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2L12 3z" />
                </svg>
                Edit with agent
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="border-b border-red-300/40 bg-red-500/10 px-5 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-auto bg-base scroll-thin">
          {file && <FileBody file={file} text={textBody} csvTab={csvTab} />}
        </div>
      </div>
    </AppShell>
  );
}

function FileBody({
  file,
  text,
  csvTab,
}: {
  file: FileInfo;
  text: string | null;
  csvTab: "table" | "chart" | "raw";
}) {
  if (!file.url) {
    return <p className="px-5 py-8 text-muted">No download URL.</p>;
  }
  if (isPdf(file.content_type)) {
    return <iframe src={file.url} className="h-full w-full bg-gray-200" title={file.name} />;
  }
  if (isImage(file.content_type)) {
    return (
      <div className="flex items-center justify-center bg-gray-100 p-8">
        <img src={file.url} alt={file.name} className="max-h-full max-w-full" />
      </div>
    );
  }
  if (isHtml(file.content_type)) {
    return (
      <iframe
        src={file.url}
        className="h-full w-full bg-white"
        sandbox="allow-scripts allow-same-origin"
        title={file.name}
      />
    );
  }
  if (isCsv(file.content_type)) {
    return <CsvView text={text} mode={csvTab} />;
  }
  if (isMarkdown(file.content_type, file.name)) {
    return (
      <article className="markdown-content mx-auto max-w-3xl px-12 py-8 text-[15px] leading-relaxed text-foreground">
        <Markdown remarkPlugins={[remarkGfm]}>{text || ""}</Markdown>
      </article>
    );
  }
  if (isText(file.content_type)) {
    return (
      <pre className="scroll-thin h-full overflow-auto px-5 py-4 font-mono text-[12.5px] text-foreground">
        {text || "Loading…"}
      </pre>
    );
  }
  return (
    <div className="mx-auto max-w-md px-8 py-12 text-center text-[13px] text-muted">
      <p className="mb-3">No inline preview for this file type.</p>
      <a
        href={file.url}
        target="_blank"
        rel="noopener noreferrer"
        className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
      >
        Open original ↗
      </a>
    </div>
  );
}

function CsvView({ text, mode }: { text: string | null; mode: "table" | "chart" | "raw" }) {
  const rows = useMemo(() => parseCsv(text || ""), [text]);
  if (!text) return <p className="px-5 py-8 text-muted">Loading…</p>;
  if (rows.length === 0) return <p className="px-5 py-8 text-muted">Empty CSV.</p>;

  if (mode === "raw") {
    return (
      <pre className="scroll-thin h-full overflow-auto px-5 py-4 font-mono text-[12px] whitespace-pre text-foreground">
        {text}
      </pre>
    );
  }
  if (mode === "chart") {
    return <CsvChart rows={rows} />;
  }
  return <CsvTable rows={rows} />;
}

function CsvTable({ rows }: { rows: string[][] }) {
  const [header, ...body] = rows;
  // Detect last numeric column for sparkline trend reference.
  const numericCols = header.map((_, ci) => body.every((r) => looksNumeric(r[ci])));
  const lastNumeric = numericCols.lastIndexOf(true);
  const seriesByRow = body.map((r) =>
    r.map((c, ci) => (numericCols[ci] ? parseFloat(c.replace(/[$,%\s]/g, "")) : NaN))
  );
  const maxByCol = header.map((_, ci) =>
    Math.max(...seriesByRow.map((s) => (Number.isFinite(s[ci]) ? Math.abs(s[ci]) : 0)))
  );

  return (
    <div className="px-5 py-5">
      <div className="overflow-hidden rounded-xl border border-border bg-base">
        <table className="w-full text-[12.5px]">
          <thead className="bg-surface">
            <tr>
              {header.map((h, i) => (
                <th
                  key={i}
                  className={
                    "border-b border-border px-4 py-2 font-medium text-muted " +
                    (numericCols[i] ? "text-right" : "text-left")
                  }
                >
                  {h}
                </th>
              ))}
              {lastNumeric >= 0 && (
                <th className="border-b border-border px-4 py-2 text-left font-medium text-muted">
                  Trend
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {body.map((row, ri) => (
              <tr key={ri} className="border-b border-border last:border-b-0 hover:bg-surface/60">
                {row.map((c, ci) => {
                  const isNum = numericCols[ci];
                  const formatted = isNum ? formatCsvNumber(c, header[ci]) : c;
                  const negative = isNum && parseFloat(c.replace(/[$,%\s]/g, "")) < 0;
                  return (
                    <td
                      key={ci}
                      className={
                        "px-4 py-2 " +
                        (isNum
                          ? "text-right font-mono " + (negative ? "text-rose-600" : "text-foreground")
                          : "text-foreground")
                      }
                    >
                      {formatted}
                    </td>
                  );
                })}
                {lastNumeric >= 0 && (
                  <td className="px-4 py-2">
                    <Sparkline
                      value={seriesByRow[ri][lastNumeric]}
                      max={maxByCol[lastNumeric] || 1}
                    />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Sparkline({ value, max }: { value: number; max: number }) {
  // Quick visual: 6 bars stepping toward this row's value (% of column max).
  const steps = [0.18, 0.32, 0.46, 0.62, 0.8, 1.0];
  const target = Math.min(1, Math.max(0.05, Math.abs(value) / max));
  return (
    <div className="flex items-end gap-0.5">
      {steps.map((s, i) => {
        const h = s * target * 100;
        return (
          <span
            key={i}
            className="w-1.5 rounded-sm bg-gradient-to-t from-[var(--color-brand-600)] to-[var(--color-brand-400)]"
            style={{ height: `${Math.max(2, h)}%`, minHeight: "2px" }}
          />
        );
      })}
    </div>
  );
}

function CsvChart({ rows }: { rows: string[][] }) {
  const [header, ...body] = rows;
  // Pick the rightmost numeric column for the chart series.
  const numericCols = header.map((_, ci) => body.every((r) => looksNumeric(r[ci])));
  const seriesIdx = numericCols.lastIndexOf(true);
  if (seriesIdx < 0) {
    return <p className="px-5 py-8 text-muted">No numeric columns to chart.</p>;
  }
  const labelIdx = numericCols.indexOf(false);
  const series = body.map((r) => parseFloat(r[seriesIdx].replace(/[$,%\s]/g, "")));
  const max = Math.max(...series.map(Math.abs));
  return (
    <div className="px-5 py-5">
      <div className="rounded-xl border border-border bg-base p-6">
        <div className="text-[11px] uppercase tracking-wide text-muted">
          {header[seriesIdx]} — by {header[labelIdx >= 0 ? labelIdx : 0]}
        </div>
        <div className="mt-4 flex h-48 items-end gap-2">
          {series.map((v, i) => {
            const h = max ? (Math.abs(v) / max) * 100 : 0;
            return (
              <div key={i} className="flex flex-1 flex-col items-center gap-1">
                <div
                  className="w-full rounded-sm bg-gradient-to-t from-[var(--color-brand-600)] to-[var(--color-brand-400)]"
                  style={{ height: `${Math.max(2, h)}%` }}
                />
                <div className="truncate text-[10px] text-muted">
                  {body[i][labelIdx >= 0 ? labelIdx : 0]}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function formatCsvNumber(value: string, header: string): string {
  const v = parseFloat(value.replace(/[$,%\s]/g, ""));
  if (!Number.isFinite(v)) return value;
  const isCurrency = /\$|arr|revenue|cost|price/i.test(header);
  if (isCurrency) {
    if (Math.abs(v) >= 1_000_000) return `${v < 0 ? "-" : ""}$${(Math.abs(v) / 1_000_000).toFixed(2)}M`;
    if (Math.abs(v) >= 1_000) return `${v < 0 ? "-" : ""}$${(Math.abs(v) / 1_000).toFixed(1)}K`;
    return `${v < 0 ? "-" : ""}$${Math.abs(v)}`;
  }
  return value;
}

function parseCsv(text: string): string[][] {
  // Minimal CSV parser — handles quoted fields with commas + escaped quotes.
  // Good enough for the demo; swap for papaparse if files get gnarlier.
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let inQuote = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuote) {
      if (c === '"' && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (c === '"') {
        inQuote = false;
      } else {
        cell += c;
      }
    } else {
      if (c === '"' && cell === "") inQuote = true;
      else if (c === ",") {
        row.push(cell);
        cell = "";
      } else if (c === "\n") {
        row.push(cell);
        rows.push(row);
        row = [];
        cell = "";
      } else if (c === "\r") {
        // ignore
      } else {
        cell += c;
      }
    }
  }
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows.filter((r) => r.some((x) => x !== ""));
}

function looksNumeric(s: string): boolean {
  if (!s) return false;
  return /^-?\$?[\d,]+(\.\d+)?%?$/.test(s.trim());
}

function formatBytes(b: number): string {
  if (!b) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}
