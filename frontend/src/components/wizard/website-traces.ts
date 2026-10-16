import { tasteUploadTraces } from "@/lib/taste-api";
import type { TraceFile } from "@/components/reward-models/trace-files";

const MAX_FILE_BYTES = 8_000_000;
const MAX_TOTAL_BYTES = 80_000_000;
const MAX_FILES = 200;

/**
 * Claude Code and Codex sessions are JSONL files, often inside hidden history
 * folders (~/.claude/projects, ~/.codex/sessions). Keep those; skip other hidden
 * files, non-JSONL files, and anything over the per-file limit.
 */
export function pickTraceFiles(files: TraceFile[]) {
  const picked: TraceFile[] = [];
  const skipped: string[] = [];
  for (const entry of files) {
    const dirs = entry.path.split("/").slice(0, -1);
    const hidden = entry.file.name.startsWith(".") || dirs.some((d) => d.startsWith(".") && d !== ".claude" && d !== ".codex");
    if (hidden || !/\.jsonl$/i.test(entry.file.name) || entry.file.size > MAX_FILE_BYTES) skipped.push(entry.path);
    else picked.push(entry);
  }
  // Newest sessions first, so a cap keeps the most recent work.
  picked.sort((a, b) => b.file.lastModified - a.file.lastModified);
  const kept: TraceFile[] = [];
  let total = 0;
  for (const entry of picked) {
    if (kept.length === MAX_FILES || total + entry.file.size > MAX_TOTAL_BYTES) { skipped.push(entry.path); continue; }
    kept.push(entry);
    total += entry.file.size;
  }
  return { kept, skipped };
}

/** Upload sessions to the website eval and return the event that tells the wizard to continue. */
export async function uploadWebsiteTraces(sessionId: string, files: TraceFile[]) {
  const { kept, skipped } = pickTraceFiles(files);
  if (!kept.length) throw new Error("No Claude Code or Codex session files (.jsonl) found.");
  const uploaded = await tasteUploadTraces(sessionId, await Promise.all(kept.map(async ({ file }) => ({ name: file.name, content: await file.text() }))));
  return {
    modelId: uploaded.model_id,
    uploaded: kept.length,
    skipped: skipped.length,
    event: `Uploaded ${kept.length} past session${kept.length === 1 ? "" : "s"}. Background job ${uploaded.job_id} is collecting their feedback. Use website_eval wait for this job and then finish to return my grading endpoint. Ask only if essential information is missing.`,
  };
}
