"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import {
  listMyWorkspaces,
  listDocuments,
  uploadDocument,
  deleteDocument,
  searchDocuments,
} from "../../lib/api";
import type { Document, DocumentChunk, Workspace } from "../../lib/types";

export default function DocumentsPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWs, setSelectedWs] = useState<string>("");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<DocumentChunk[]>([]);
  const [searching, setSearching] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadWorkspaces = useCallback(async () => {
    try {
      const res = await listMyWorkspaces();
      const ws = res?.workspaces ?? [];
      setWorkspaces(ws);
      if (ws.length > 0 && !selectedWs) setSelectedWs(ws[0].id);
    } catch {}
  }, [selectedWs]);

  const loadDocuments = useCallback(async () => {
    if (!selectedWs) return;
    try {
      const docs = await listDocuments(selectedWs);
      setDocuments(docs);
    } catch {}
  }, [selectedWs]);

  useEffect(() => {
    if (user) loadWorkspaces();
  }, [user, loadWorkspaces]);

  useEffect(() => {
    if (selectedWs) {
      loadDocuments();
      setSearchResults([]);
      setSearchQuery("");
    }
  }, [selectedWs, loadDocuments]);

  // Auto-refresh while any document is pending/processing
  useEffect(() => {
    const hasPending = documents.some(
      (d) => d.status === "pending" || d.status === "processing"
    );
    if (!hasPending || !selectedWs) return;
    const interval = setInterval(loadDocuments, 5000);
    return () => clearInterval(interval);
  }, [documents, selectedWs, loadDocuments]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedWs) return;
    setUploading(true);
    setError("");
    try {
      await uploadDocument(selectedWs, file);
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDelete = async (docId: string) => {
    if (!selectedWs || !confirm("Delete this document?")) return;
    try {
      await deleteDocument(selectedWs, docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleSearch = async () => {
    if (!selectedWs || !searchQuery.trim()) return;
    setSearching(true);
    try {
      const chunks = await searchDocuments(selectedWs, searchQuery.trim());
      setSearchResults(chunks);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
    setSearching(false);
  };

  const statusColor = (s: string) => {
    if (s === "ready") return "text-green-400 bg-green-400/10";
    if (s === "processing") return "text-yellow-400 bg-yellow-400/10";
    if (s === "error") return "text-red-400 bg-red-400/10";
    return "text-muted bg-raised";
  };

  const fileTypeIcon = (t: string) => {
    if (t === "pdf") return "P";
    if (["png", "jpg", "jpeg", "gif", "webp"].includes(t)) return "I";
    if (["doc", "docx"].includes(t)) return "W";
    if (t === "md" || t === "txt") return "T";
    return "F";
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-4xl mx-auto w-full px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-foreground font-display">Documents</h1>
          <div className="flex items-center gap-2">
            <select
              value={selectedWs}
              onChange={(e) => setSelectedWs(e.target.value)}
              className="text-sm bg-surface border border-border rounded px-2 py-1.5 text-foreground"
            >
              {workspaces.map((ws) => (
                <option key={ws.id} value={ws.id}>{ws.name}</option>
              ))}
            </select>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || !selectedWs}
              className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded disabled:opacity-50"
            >
              {uploading ? "Uploading..." : "Upload"}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,.doc,.docx,.txt,.md,.csv"
              className="hidden"
              onChange={handleUpload}
            />
          </div>
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        {/* Search */}
        <div className="flex gap-2 mb-6">
          <input
            type="text"
            placeholder="Search across all documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="flex-1 text-sm bg-surface border border-border rounded px-3 py-2 text-foreground placeholder:text-muted"
          />
          <button
            onClick={handleSearch}
            disabled={searching || !searchQuery.trim()}
            className="text-sm bg-raised hover:bg-border text-foreground px-3 py-2 rounded disabled:opacity-50"
          >
            {searching ? "Searching..." : "Search"}
          </button>
        </div>

        {/* Search Results */}
        {searchResults.length > 0 && (
          <section className="mb-8">
            <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-3">
              Search Results ({searchResults.length})
            </h2>
            <div className="space-y-3">
              {searchResults.map((chunk, i) => (
                <div key={i} className="bg-surface border border-border rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs font-medium text-brand">{chunk.doc_name}</span>
                    <span className="text-xs text-muted">
                      similarity: {(chunk.similarity * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="text-sm text-foreground whitespace-pre-wrap">{chunk.content}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Document List */}
        {documents.length === 0 ? (
          <p className="text-muted text-sm">
            No documents yet. Upload PDFs, images, or other files for AI-powered search and retrieval.
          </p>
        ) : (
          <div className="space-y-1">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="group flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-raised transition-colors"
              >
                <div className="w-7 h-7 rounded-md bg-brand/15 text-brand flex items-center justify-center text-xs font-bold flex-shrink-0">
                  {fileTypeIcon(doc.file_type)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-foreground truncate">{doc.name}</div>
                  <div className="text-xs text-muted">
                    {doc.file_type}
                    {(doc.metadata as Record<string, number>)?.chunk_count
                      ? ` \u00b7 ${(doc.metadata as Record<string, number>).chunk_count} chunks`
                      : ""}
                  </div>
                </div>
                <span className={`text-[10px] px-1.5 py-0.5 rounded flex-shrink-0 ${statusColor(doc.status)}`}>
                  {doc.status}
                </span>
                <span className="text-xs text-muted flex-shrink-0">
                  {new Date(doc.created_at).toLocaleDateString()}
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(doc.id); }}
                  className="text-xs text-muted hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
