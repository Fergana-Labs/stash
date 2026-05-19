"use client";

import { useState } from "react";

import {
  TaskStatus,
  importGitRepo,
  waitForTask,
} from "@/lib/integrations";

type Props = {
  workspaceId: string;
  folderId?: string | null;
  /** Called once the task reaches a terminal state. */
  onDone?: (status: TaskStatus) => void;
  onClose: () => void;
};

/**
 * Modal form for kicking off a git import. Accepts any URL the backend
 * supports (github.com, gitlab.com, bitbucket.org, direct .zip). The
 * "Connect GitHub" affordance for private GitHub repos lives in the
 * /settings/integrations page — this dialog only takes the URL +
 * optional PAT for non-connected hosts.
 */
export default function GitImportDialog({
  workspaceId,
  folderId,
  onDone,
  onClose,
}: Props) {
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [subpath, setSubpath] = useState("");
  const [pat, setPat] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const { task_id } = await importGitRepo(workspaceId, {
        url: url.trim(),
        ref: ref.trim() || undefined,
        subpath: subpath.trim() || undefined,
        pat: pat.trim() || undefined,
        folder_id: folderId || undefined,
      });
      const final = await waitForTask(task_id, setTaskStatus, 1500);
      if (final.state === "FAILURE") {
        setError(final.error || "Import failed");
      } else {
        onDone?.(final);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(560px, 92vw)",
          background: "var(--surface, white)",
          borderRadius: 12,
          padding: 24,
          boxShadow: "0 24px 48px rgba(0,0,0,0.18)",
        }}
      >
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>Import from git</h2>
        <p style={{ fontSize: 13, color: "var(--muted, #6b7280)", marginBottom: 16 }}>
          GitHub, GitLab, Bitbucket, or any direct <code>.zip</code> URL.
          Markdown becomes pages; other files become attachments with text
          extraction queued automatically.
        </p>

        <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <label style={{ fontSize: 13 }}>
            Repository URL
            <input
              type="url"
              required
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/org/repo"
              disabled={submitting}
              style={{
                display: "block",
                width: "100%",
                marginTop: 4,
                padding: "8px 10px",
                borderRadius: 6,
                border: "1px solid var(--border, #d1d5db)",
              }}
            />
          </label>

          <div style={{ display: "flex", gap: 12 }}>
            <label style={{ fontSize: 13, flex: 1 }}>
              Branch / ref (optional)
              <input
                type="text"
                value={ref}
                onChange={(e) => setRef(e.target.value)}
                placeholder="main"
                disabled={submitting}
                style={{
                  display: "block",
                  width: "100%",
                  marginTop: 4,
                  padding: "8px 10px",
                  borderRadius: 6,
                  border: "1px solid var(--border, #d1d5db)",
                }}
              />
            </label>
            <label style={{ fontSize: 13, flex: 1 }}>
              Subpath (optional)
              <input
                type="text"
                value={subpath}
                onChange={(e) => setSubpath(e.target.value)}
                placeholder="docs/"
                disabled={submitting}
                style={{
                  display: "block",
                  width: "100%",
                  marginTop: 4,
                  padding: "8px 10px",
                  borderRadius: 6,
                  border: "1px solid var(--border, #d1d5db)",
                }}
              />
            </label>
          </div>

          <label style={{ fontSize: 13 }}>
            Personal access token (optional — private repos only)
            <input
              type="password"
              value={pat}
              onChange={(e) => setPat(e.target.value)}
              autoComplete="off"
              placeholder="ghp_… / glpat_… — never stored"
              disabled={submitting}
              style={{
                display: "block",
                width: "100%",
                marginTop: 4,
                padding: "8px 10px",
                borderRadius: 6,
                border: "1px solid var(--border, #d1d5db)",
                fontFamily: "var(--font-mono, monospace)",
              }}
            />
            <span style={{ fontSize: 12, color: "var(--muted, #6b7280)" }}>
              For GitHub, connect from Settings → Integrations instead — the
              stored OAuth token will be used automatically.
            </span>
          </label>

          {taskStatus && (
            <div
              style={{
                fontSize: 13,
                padding: 8,
                borderRadius: 6,
                background: "var(--info-bg, rgba(37,99,235,0.08))",
              }}
            >
              Import status: <strong>{taskStatus.state}</strong>
              {taskStatus.state === "SUCCESS" &&
                taskStatus.result != null &&
                typeof taskStatus.result === "object" && (
                  <pre
                    style={{
                      fontSize: 12,
                      marginTop: 6,
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {JSON.stringify(taskStatus.result as Record<string, unknown>, null, 2)}
                  </pre>
                )}
            </div>
          )}

          {error && (
            <div
              style={{
                fontSize: 13,
                padding: 8,
                borderRadius: 6,
                background: "rgba(220,38,38,0.08)",
                color: "rgb(185,28,28)",
              }}
            >
              {error}
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              style={{
                padding: "8px 14px",
                borderRadius: 6,
                border: "1px solid var(--border, #d1d5db)",
                background: "transparent",
                cursor: submitting ? "wait" : "pointer",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !url.trim()}
              style={{
                padding: "8px 14px",
                borderRadius: 6,
                border: "1px solid var(--accent, #2563eb)",
                background: "var(--accent, #2563eb)",
                color: "white",
                cursor: submitting ? "wait" : !url.trim() ? "not-allowed" : "pointer",
                opacity: !url.trim() ? 0.6 : 1,
              }}
            >
              {submitting ? "Importing…" : "Import"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
