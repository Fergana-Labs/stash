"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import { listFiles, deleteFile, uploadFile } from "../../lib/api";
import type { FileInfo } from "../../lib/types";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

const ICON_MAP: Record<string, string> = {
  "image/": "img",
  "application/pdf": "PDF",
  "text/": "TXT",
};

function getFileIcon(contentType: string): string {
  for (const [prefix, icon] of Object.entries(ICON_MAP)) {
    if (contentType.startsWith(prefix)) return icon;
  }
  return "FILE";
}

export default function FilesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = searchParams.get("ws");
  const { user, loading, logout } = useAuth();
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [filesLoading, setFilesLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadFiles = useCallback(async () => {
    if (!workspaceId) return;
    setFilesLoading(true);
    try {
      setFiles(await listFiles(workspaceId));
    } catch {
      setFiles([]);
    }
    setFilesLoading(false);
  }, [workspaceId]);

  useEffect(() => {
    if (user && workspaceId) loadFiles();
  }, [user, workspaceId, loadFiles]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !workspaceId) return;
    setUploading(true);
    try {
      await uploadFile(workspaceId, file);
      await loadFiles();
    } catch { /* ignore */ }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDelete = async (fileId: string, name: string) => {
    if (!workspaceId || !confirm(`Delete "${name}"?`)) return;
    try {
      await deleteFile(workspaceId, fileId);
      await loadFiles();
    } catch { /* ignore */ }
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) { router.push("/login"); return null; }
  if (!workspaceId) return <div className="min-h-screen flex items-center justify-center text-muted">No workspace selected</div>;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-4xl mx-auto w-full px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <button onClick={() => router.push(`/workspaces/${workspaceId}`)} className="text-sm text-dim hover:text-foreground mb-1">&larr; Workspace</button>
            <h1 className="text-xl font-bold text-foreground font-display">Files</h1>
          </div>
          <div>
            <input ref={fileInputRef} type="file" className="hidden" onChange={handleUpload} />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="text-xs bg-brand hover:bg-brand-hover text-white px-3 py-1.5 rounded disabled:opacity-50"
            >
              {uploading ? "Uploading..." : "Upload file"}
            </button>
          </div>
        </div>

        {filesLoading ? (
          <p className="text-sm text-muted">Loading files...</p>
        ) : files.length === 0 ? (
          <div className="text-center py-16 text-muted">
            <p className="text-sm">No files uploaded yet.</p>
            <p className="text-xs mt-1">Upload files here or drag images into wiki pages.</p>
          </div>
        ) : (
          <div className="border border-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface border-b border-border text-left">
                  <th className="px-4 py-2 text-xs font-medium text-muted uppercase tracking-wider">Name</th>
                  <th className="px-4 py-2 text-xs font-medium text-muted uppercase tracking-wider">Type</th>
                  <th className="px-4 py-2 text-xs font-medium text-muted uppercase tracking-wider">Size</th>
                  <th className="px-4 py-2 text-xs font-medium text-muted uppercase tracking-wider">Uploaded</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.id} className="border-b border-border/50 hover:bg-raised/50 transition-colors group">
                    <td className="px-4 py-2.5">
                      <a href={f.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-foreground hover:text-brand">
                        <span className="w-7 h-7 rounded bg-raised flex items-center justify-center text-[10px] font-bold text-muted flex-shrink-0">
                          {getFileIcon(f.content_type)}
                        </span>
                        <span className="truncate">{f.name}</span>
                      </a>
                    </td>
                    <td className="px-4 py-2.5 text-muted text-xs font-mono">{f.content_type.split("/").pop()}</td>
                    <td className="px-4 py-2.5 text-muted text-xs font-mono">{formatBytes(f.size_bytes)}</td>
                    <td className="px-4 py-2.5 text-muted text-xs">{formatDate(f.created_at)}</td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        onClick={() => handleDelete(f.id, f.name)}
                        className="text-xs text-red-400/50 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}
