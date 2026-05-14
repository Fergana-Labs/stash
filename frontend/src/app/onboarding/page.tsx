"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import Header from "../../components/Header";
import { useAuth } from "../../hooks/useAuth";
import { getToken, listMyWorkspaces } from "../../lib/api";

// Read the token from localStorage in an SSR-safe way. `useSyncExternalStore`
// gives us the right value on first client render and re-runs on storage
// events, without setState-in-effect.
function useStashToken(): string | null {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener("storage", cb);
      return () => window.removeEventListener("storage", cb);
    },
    () => getToken(),
    () => null,
  );
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

const TOPIC_PLACEHOLDER = "<your topic — e.g. 'how our rate limiter works'>";

function buildPromptBlock(apiKey: string, apiUrl: string): string {
  return `Make an HTML page about ${TOPIC_PLACEHOLDER}. Make it information-dense, use SVG diagrams where they help, and optimize it to be read once.

When you're done, publish it to Stash and print the share URL by running:

curl -sS -X POST ${apiUrl}/api/v1/publish \\
  -H "Authorization: Bearer ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d @- <<'EOF'
{
  "title": "<your title>",
  "content_type": "html",
  "content": "<your generated HTML>",
  "audience": "link"
}
EOF`;
}

export default function OnboardingPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const apiKey = useStashToken();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!loading && apiKey === null) {
      router.replace("/login");
    }
  }, [loading, apiKey, router]);

  const promptBlock = apiKey ? buildPromptBlock(apiKey, API_URL) : "";

  async function handleCopy() {
    if (!promptBlock) return;
    await navigator.clipboard.writeText(promptBlock);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function handleSkip() {
    const { workspaces } = await listMyWorkspaces();
    if (workspaces.length > 0) {
      router.push(`/workspaces/${workspaces[0].id}`);
    } else {
      router.push("/");
    }
  }

  if (loading || !apiKey) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading…</div>;
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 px-4 py-12">
        <div className="mx-auto w-full max-w-2xl space-y-8">
          <div className="space-y-3 text-center">
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-surface border border-border text-[10px] font-mono uppercase tracking-[0.18em] text-muted">
              <span className="w-1 h-1 rounded-full bg-brand animate-pulse" />
              Step 1 of 1
            </div>
            <h1 className="font-display text-[32px] leading-[1.05] font-bold tracking-tight text-foreground">
              Make your first page
            </h1>
            <p className="text-sm text-dim max-w-md mx-auto">
              Paste this into Claude Code, Cursor, or Codex. Your agent will write the
              HTML and publish it. You&rsquo;ll get a share URL back.
            </p>
          </div>

          <div className="rounded-2xl border border-border bg-surface overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-background/40">
              <div className="text-[11px] font-mono uppercase tracking-wider text-muted">
                Prompt + curl
              </div>
              <button
                type="button"
                onClick={handleCopy}
                className="text-[11px] font-medium text-brand hover:text-brand-hover transition-colors"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <pre className="p-4 text-[12px] leading-relaxed text-foreground font-mono whitespace-pre-wrap break-all overflow-x-auto">
              {promptBlock}
            </pre>
          </div>

          <div className="rounded-xl border border-border-subtle bg-background/40 p-4 text-[12px] text-dim leading-relaxed">
            <strong className="text-foreground font-medium">What happens next:</strong>{" "}
            your agent generates HTML and runs the curl command. The response prints a
            URL like <code className="text-foreground">https://app.joinstash.ai/v/abc123</code>.
            Open it &mdash; your page is live and shareable. We&rsquo;ll help you bring
            teammates in from there.
          </div>

          <div className="text-center">
            <button
              type="button"
              onClick={handleSkip}
              className="text-[12px] text-muted hover:text-foreground transition-colors"
            >
              Skip &mdash; just take me to my workspace
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
