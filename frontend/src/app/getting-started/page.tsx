"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import {
  createPersonalNotebook,
  createPersonalPage,
} from "../../lib/api";
import { parseBookmarkHTML, type ParsedBookmark } from "../../lib/bookmark-parser";

export default function GettingStartedPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [bookmarks, setBookmarks] = useState<ParsedBookmark[]>([]);
  const [importing, setImporting] = useState(false);
  const [imported, setImported] = useState(0);
  const [total, setTotal] = useState(0);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const html = e.target?.result as string;
      const parsed = parseBookmarkHTML(html);
      setBookmarks(parsed);
    };
    reader.readAsText(file);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleImport = useCallback(async () => {
    if (!bookmarks.length) return;
    setImporting(true);
    setTotal(bookmarks.length);
    setImported(0);
    setError("");

    try {
      // Create notebook
      let notebook;
      try {
        notebook = await createPersonalNotebook("Bookmarks");
      } catch {
        // May already exist, try to find it
        const { listPersonalNotebooks } = await import("../../lib/api");
        const res = await listPersonalNotebooks();
        notebook = (res.notebooks || []).find((n: { name: string }) => n.name === "Bookmarks");
        if (!notebook) throw new Error("Could not create or find Bookmarks notebook");
      }

      // Import bookmarks as pages (batched, 5 at a time)
      let count = 0;
      for (let i = 0; i < bookmarks.length; i += 5) {
        const batch = bookmarks.slice(i, i + 5);
        await Promise.allSettled(
          batch.map(async (bm) => {
            const content = `# ${bm.title}\n\n[${bm.url}](${bm.url})\n\nFolder: ${bm.folder}`;
            try {
              await createPersonalPage(notebook.id, bm.title.slice(0, 200), content);
              count++;
            } catch {
              // Skip duplicates or failures
            }
          })
        );
        setImported(Math.min(i + 5, bookmarks.length));
      }

      setImported(count);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    }
    setImporting(false);
  }, [bookmarks]);

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-2xl mx-auto w-full px-4 py-12">
        <h1 className="text-3xl font-bold text-foreground font-display mb-2">
          Get Started
        </h1>
        <p className="text-dim mb-8">
          Turn your bookmarks into a searchable, auto-curating knowledge base.
        </p>

        {/* Step 1: Import Bookmarks */}
        <div className="bg-surface border border-border rounded-lg p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <span className="w-8 h-8 rounded-full bg-brand text-white flex items-center justify-center text-sm font-bold">1</span>
            <h2 className="text-lg font-medium text-foreground">Import your bookmarks</h2>
          </div>

          {!bookmarks.length && !done ? (
            <div
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-border rounded-lg p-10 text-center cursor-pointer hover:border-brand hover:bg-brand/5 transition-colors"
            >
              <p className="text-foreground mb-2">
                Drop your bookmarks .html file here
              </p>
              <p className="text-sm text-muted">
                Chrome: Bookmarks &rarr; ... &rarr; Export bookmarks
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".html,.htm"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFile(file);
                }}
              />
            </div>
          ) : bookmarks.length > 0 && !done ? (
            <div>
              <p className="text-foreground mb-3">
                Found <strong>{bookmarks.length}</strong> bookmarks.
              </p>
              <div className="max-h-[200px] overflow-y-auto bg-raised rounded p-3 mb-4">
                {bookmarks.slice(0, 20).map((bm, i) => (
                  <div key={i} className="text-xs text-dim truncate py-0.5">
                    <span className="text-muted">{bm.folder}</span>
                    {" / "}
                    {bm.title}
                  </div>
                ))}
                {bookmarks.length > 20 && (
                  <div className="text-xs text-muted py-0.5">
                    ...and {bookmarks.length - 20} more
                  </div>
                )}
              </div>

              {importing ? (
                <div>
                  <div className="w-full bg-raised rounded-full h-2 mb-2">
                    <div
                      className="bg-brand h-2 rounded-full transition-all"
                      style={{ width: `${(imported / total) * 100}%` }}
                    />
                  </div>
                  <p className="text-xs text-muted">Importing... {imported}/{total}</p>
                </div>
              ) : (
                <div className="flex gap-3">
                  <button
                    onClick={handleImport}
                    className="bg-brand hover:bg-brand-hover text-foreground px-4 py-2 rounded text-sm"
                  >
                    Import {bookmarks.length} bookmarks
                  </button>
                  <button
                    onClick={() => setBookmarks([])}
                    className="text-sm text-muted hover:text-foreground"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          ) : done ? (
            <div className="text-center py-4">
              <p className="text-green-400 text-lg mb-1">Imported {imported} bookmarks</p>
              <p className="text-sm text-muted">The sleep agent will curate them into a wiki.</p>
            </div>
          ) : null}

          {error && <p className="text-red-400 text-sm mt-3">{error}</p>}
        </div>

        {/* Step 2: Connect Claude Code */}
        <div className="bg-surface border border-border rounded-lg p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <span className="w-8 h-8 rounded-full bg-raised text-muted flex items-center justify-center text-sm font-bold">2</span>
            <h2 className="text-lg font-medium text-foreground">Connect Claude Code</h2>
          </div>
          <p className="text-sm text-dim mb-3">
            Make every AI session searchable. Install the CLI and connect:
          </p>
          <div className="bg-raised rounded p-3 font-mono text-xs text-foreground">
            <div>pip install boozle</div>
            <div>boozle auth https://getboozle.com --api-key YOUR_KEY</div>
          </div>
        </div>

        {/* Step 3: Search */}
        <div className="bg-surface border border-border rounded-lg p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <span className="w-8 h-8 rounded-full bg-raised text-muted flex items-center justify-center text-sm font-bold">3</span>
            <h2 className="text-lg font-medium text-foreground">Search your knowledge</h2>
          </div>
          <p className="text-sm text-dim mb-4">
            Your data is being embedded and curated. Try searching:
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => router.push("/search")}
              className="bg-brand hover:bg-brand-hover text-foreground px-4 py-2 rounded text-sm"
            >
              Open Search
            </button>
            <button
              onClick={() => router.push("/notebooks")}
              className="bg-raised hover:bg-border text-foreground px-3 py-2 rounded text-sm"
            >
              Browse Notebooks
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
