import { tasteUploadTraces } from "@/lib/taste-api";
import type { TraceFile } from "@/components/reward-models/trace-files";

const MAX_SOURCE_BYTES = 400_000_000;
const MAX_FILE_CHARS = 40_000_000;
const MAX_TOTAL_CHARS = 80_000_000;
const MAX_FILES = 200;
const MAX_TOOL_TEXT = 4000;
const MAX_IMAGE_SIDE = 1600;
const SHRINK_ABOVE = 300_000;

/**
 * Claude Code and Codex sessions are JSONL files, often inside hidden history
 * folders (~/.claude/projects, ~/.codex/sessions). Keep those; skip other hidden
 * files, non-JSONL files, and anything too large to read.
 */
export function pickTraceFiles(files: TraceFile[]) {
  const picked: TraceFile[] = [];
  const skipped: string[] = [];
  for (const entry of files) {
    const dirs = entry.path.split("/").slice(0, -1);
    const hidden = entry.file.name.startsWith(".") || dirs.some((d) => d.startsWith(".") && d !== ".claude" && d !== ".codex");
    if (hidden || !/\.jsonl$/i.test(entry.file.name) || entry.file.size > MAX_SOURCE_BYTES) skipped.push(entry.path);
    else picked.push(entry);
  }
  // Newest sessions first, so a cap keeps the most recent work.
  picked.sort((a, b) => b.file.lastModified - a.file.lastModified);
  return { kept: picked.slice(0, MAX_FILES), skipped: [...skipped, ...picked.slice(MAX_FILES).map((p) => p.path)] };
}

const KEEP = new Set(["message", "function_call", "custom_tool_call", "function_call_output", "custom_tool_call_output"]);

/** Re-encode a large screenshot as a smaller JPEG. Returns the original when the browser can't. */
async function shrinkImage(url: string): Promise<string> {
  if (url.length < SHRINK_ABOVE || typeof createImageBitmap === "undefined" || typeof OffscreenCanvas === "undefined") return url;
  try {
    const bitmap = await createImageBitmap(await (await fetch(url)).blob());
    const scale = Math.min(1, MAX_IMAGE_SIDE / Math.max(bitmap.width, bitmap.height));
    const canvas = new OffscreenCanvas(Math.round(bitmap.width * scale), Math.round(bitmap.height * scale));
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await canvas.convertToBlob({ type: "image/jpeg", quality: 0.85 });
    const shrunk = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
    return shrunk.length < url.length ? shrunk : url;
  } catch {
    return url;
  }
}

/**
 * Keep only what the taste pipeline reads from a Codex session: messages (with
 * their screenshots, shrunk) and tool calls/results (clipped). Context
 * compaction records and telemetry are most of a session's size and unused.
 */
export async function compactSession(text: string): Promise<string> {
  const out: string[] = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    let row: { type?: string; payload?: Record<string, unknown> };
    try { row = JSON.parse(line); } catch { continue; }
    const payload = row.payload;
    if (row.type === "session_meta") { out.push(line); continue; }
    if (row.type !== "response_item" || !payload || !KEEP.has(String(payload.type))) continue;
    for (const key of ["output", "arguments", "input"]) {
      const value = payload[key];
      if (typeof value === "string" && value.length > MAX_TOOL_TEXT) payload[key] = value.slice(0, MAX_TOOL_TEXT);
    }
    if (payload.type === "message" && Array.isArray(payload.content)) {
      for (const part of payload.content as Record<string, unknown>[]) {
        const url = typeof part?.image_url === "string" ? part.image_url : null;
        if (url?.startsWith("data:image/")) part.image_url = await shrinkImage(url);
      }
    }
    out.push(JSON.stringify(row));
  }
  return out.join("\n");
}

/** Upload sessions to the website eval and return the event that tells the wizard to continue. */
export async function uploadWebsiteTraces(sessionId: string, files: TraceFile[], onProgress?: (text: string) => void) {
  const { kept, skipped } = pickTraceFiles(files);
  if (!kept.length) throw new Error("No Codex session files (.jsonl) found.");
  const payload: { name: string; content: string }[] = [];
  let total = 0;
  for (const [i, { file, path }] of kept.entries()) {
    onProgress?.(`Reading session ${i + 1} of ${kept.length}…`);
    const content = await compactSession(await file.text());
    if (!content || content.length > MAX_FILE_CHARS || total + content.length > MAX_TOTAL_CHARS) { skipped.push(path); continue; }
    payload.push({ name: file.name, content });
    total += content.length;
  }
  if (!payload.length) throw new Error("These sessions are too large to upload, even after removing tool output.");
  onProgress?.(`Uploading ${payload.length} session${payload.length === 1 ? "" : "s"}…`);
  const uploaded = await tasteUploadTraces(sessionId, payload);
  return {
    modelId: uploaded.model_id,
    uploaded: payload.length,
    skipped: skipped.length,
    event: `Uploaded ${payload.length} past session${payload.length === 1 ? "" : "s"}.`,
  };
}
