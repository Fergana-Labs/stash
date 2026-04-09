"use client";

import { useState } from "react";

interface SetupCardProps {
  workspaceId: string;
  apiKey?: string | null;
}

const DISMISS_KEY_PREFIX = "octopus_setup_dismissed_";

export default function SetupCard({ workspaceId, apiKey }: SetupCardProps) {
  const storageKey = `${DISMISS_KEY_PREFIX}${workspaceId}`;
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(storageKey) === "1";
  });
  const [copied, setCopied] = useState<string | null>(null);

  if (dismissed) return null;

  const handleDismiss = () => {
    localStorage.setItem(storageKey, "1");
    setDismissed(true);
  };

  const copyText = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(label);
    } catch {
      setCopied(label);
    }
    setTimeout(() => setCopied(null), 2000);
  };

  const pluginCmd = "claude plugin add ./claude-plugin";
  const connectCmd = "/octopus:connect";
  const mcpCmd = apiKey
    ? `claude mcp add --transport http octopus https://getboozle.com/mcp \\\n  --header "Authorization: Bearer ${apiKey}"`
    : `claude mcp add --transport http octopus https://getboozle.com/mcp \\\n  --header "Authorization: Bearer YOUR_API_KEY"`;

  return (
    <div className="bg-[#1a2332] border border-white/10 rounded-lg overflow-hidden mb-8">
      <div className="px-5 py-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-slate-100 uppercase tracking-wider font-mono">
            Connect your first agent
          </h3>
          <button
            onClick={handleDismiss}
            className="text-xs text-slate-400 hover:text-slate-100 transition-colors"
          >
            Dismiss
          </button>
        </div>

        <div className="space-y-3">
          {/* Plugin method */}
          <div>
            <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1.5 font-mono">
              Claude Code plugin
            </div>
            <div className="bg-[#0f1720] rounded-md px-4 py-3 font-mono text-sm text-slate-300 flex items-start justify-between gap-3">
              <div className="space-y-1">
                <div>
                  <span className="text-slate-500 select-none">$ </span>
                  {pluginCmd}
                </div>
                <div>
                  <span className="text-slate-500 select-none">$ </span>
                  <span className="text-orange-400">{connectCmd}</span>
                </div>
              </div>
              <button
                onClick={() => copyText(`${pluginCmd}\n${connectCmd}`, "plugin")}
                className="text-[10px] text-slate-400 hover:text-slate-100 px-2 py-1 rounded border border-white/10 hover:border-white/20 transition-colors flex-shrink-0"
              >
                {copied === "plugin" ? "Copied" : "Copy"}
              </button>
            </div>
          </div>

          {/* MCP method */}
          <div>
            <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1.5 font-mono">
              Or add the MCP server
            </div>
            <div className="bg-[#0f1720] rounded-md px-4 py-3 font-mono text-sm text-slate-300 flex items-start justify-between gap-3">
              <pre className="whitespace-pre-wrap text-xs leading-relaxed"><span className="text-slate-500 select-none">$ </span>{mcpCmd}</pre>
              <button
                onClick={() => copyText(mcpCmd, "mcp")}
                className="text-[10px] text-slate-400 hover:text-slate-100 px-2 py-1 rounded border border-white/10 hover:border-white/20 transition-colors flex-shrink-0"
              >
                {copied === "mcp" ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
        </div>

        <p className="text-xs text-slate-400 mt-3">
          The plugin auto-streams every tool call, edit, and message to this workspace.{" "}
          <a href="/docs/quickstart" className="text-orange-400 hover:text-orange-300 hover:underline">
            Full quickstart →
          </a>
        </p>
      </div>
    </div>
  );
}
