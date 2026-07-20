"use client";

import { ChevronDown, FileText, TerminalSquare } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { connectorIcon, labelForProvider } from "@/components/integrations/connectors";

// The native handles come first, then the user's connected providers.
const NATIVE_LABELS: Record<string, string> = { files: "Files", sessions: "Sessions" };

function tokenLabel(token: string): string {
  return NATIVE_LABELS[token] ?? labelForProvider(token);
}

function tokenIcon(token: string) {
  if (token === "files") return <FileText className="size-4" />;
  if (token === "sessions") return <TerminalSquare className="size-4" />;
  return connectorIcon(token);
}

export default function SearchSourceFilter({
  tokens,
  deselected,
  onToggle,
}: {
  tokens: string[];
  deselected: Set<string>;
  onToggle: (token: string) => void;
}) {
  const selectedCount = tokens.filter((t) => !deselected.has(t)).length;
  const label =
    selectedCount === tokens.length ? "All sources" : `Sources · ${selectedCount}/${tokens.length}`;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Sources"
        className="flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-[12.5px] text-foreground hover:border-[var(--color-brand-300)]"
      >
        {label}
        <ChevronDown className="size-3.5 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-48 text-[12.5px]">
        {tokens.map((token) => (
          <DropdownMenuCheckboxItem
            key={token}
            checked={!deselected.has(token)}
            onCheckedChange={() => onToggle(token)}
            // Keep the menu open — picking sources is a multi-toggle gesture.
            onSelect={(e) => e.preventDefault()}
          >
            <span className="flex size-4 items-center justify-center">{tokenIcon(token)}</span>
            {tokenLabel(token)}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
