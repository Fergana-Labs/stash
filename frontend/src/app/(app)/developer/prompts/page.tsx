"use client";

import { useEffect, useState } from "react";
import { Check, ChevronDown, ChevronRight, Copy, KeyRound, Plus } from "lucide-react";

import { cn } from "@/lib/utils";

import DeveloperGate from "@/components/developer/DeveloperGate";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CodeBlock, PageHeading, SectionHeading } from "@/components/developer/DocsPrimitives";
import MintKeyDialog from "@/components/developer/MintKeyDialog";
import {
  BACKFILL_PROMPT,
  INSTALL_KEY_TOKEN,
  renderInstallPrompt,
} from "@/components/developer/agentPrompts";
import { listDeveloperKeys, type DeveloperKey } from "@/lib/api";

export default function DeveloperPrompts() {
  return (
    <DeveloperGate>
      <PageHeading title="Prompts">
        You don&apos;t integrate Stash by hand — your coding agent does. Pick the API key the
        prompt should use — or mint one right here — then paste it into your agent, pointed
        at your codebase.
      </PageHeading>

      <InstallSection />

      <Advanced>
        <PromptSection
          title="Backfill only"
          blurb="For a stash that is already installed. Install covers your history on the way
            in — reach for this only when there is history left to load: you skipped it
            during install, or you've since imported another database."
          prompt={BACKFILL_PROMPT}
        />
      </Advanced>
    </DeveloperGate>
  );
}

/** The Install prompt with the key chosen inline: a dropdown sits in the
 *  prompt text itself, right where the key is named. A key minted here still
 *  has its material (the only moment it exists), so the copied prompt carries
 *  the key; an existing key is pinned by name and must already be in the
 *  app's env. No key, no copy. */
function InstallSection() {
  const [keys, setKeys] = useState<DeveloperKey[] | null>(null);
  // "new" = the key minted on this page; otherwise a key id from the list.
  const [selected, setSelected] = useState<string>("");
  const [mintedKey, setMintedKey] = useState<{ name: string; api_key: string } | null>(null);
  const [minting, setMinting] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    listDeveloperKeys()
      .then((res) => {
        setKeys(res.keys);
        // Newest first: the prompt binds to the most recent key by default.
        if (res.keys.length > 0) setSelected(res.keys[0].id);
      })
      .catch(() => setKeys([]));
  }, []);

  const selectedKey = keys?.find((k) => k.id === selected) ?? null;
  const usingMinted = selected === "new" && mintedKey !== null;
  const hasKey = usingMinted || selectedKey !== null;

  // What follows the dropdown, in both the display and the copied text.
  const keyTail = usingMinted
    ? `. The key is:\n   ${mintedKey.api_key}\nPut it in this app's env as STASH_API_KEY and never commit it.`
    : hasKey
      ? ` — it should already be in this app's env as STASH_API_KEY;\nif it isn't set, stop and ask me for it.`
      : ` as $STASH_API_KEY.`;

  // The dropdown's textual stand-in for the copied prompt.
  const keyRef = usingMinted
    ? `the key "${mintedKey.name}" we just minted`
    : selectedKey
      ? `the Stash key named "${selectedKey.name}"` +
        (selectedKey.key_prefix ? ` (${selectedKey.key_prefix}…${selectedKey.key_suffix})` : "")
      : "<an API key>";

  const keyLabel = usingMinted
    ? `${mintedKey.name} (just minted)`
    : selectedKey
      ? selectedKey.name +
        (selectedKey.key_prefix ? ` · ${selectedKey.key_prefix}…${selectedKey.key_suffix}` : "")
      : "choose a key…";

  const copyText = renderInstallPrompt(`Use ${keyRef}${keyTail}`);
  const [before, after] = renderInstallPrompt(INSTALL_KEY_TOKEN).split(INSTALL_KEY_TOKEN);

  function copy() {
    navigator.clipboard.writeText(copyText);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className="mb-12">
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading>Install</SectionHeading>
        <button
          onClick={copy}
          disabled={!hasKey}
          title={hasKey ? undefined : "Create an API key first — the prompt needs one"}
          className="flex shrink-0 items-center gap-2 rounded-sm bg-brand-500 px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-muted-foreground/30"
        >
          <Copy className="h-3.5 w-3.5" />
          {copied ? "Copied" : "Copy prompt"}
        </button>
      </div>
      <p className="mt-2 max-w-2xl text-[13.5px] leading-6 text-muted-foreground">
        The whole onboarding in one prompt: the memory read before each turn, the transcript
        upload after it, a backfill of whatever history your database already holds, and a
        final check that a user shows up in this console. Pick the key in the prompt itself.
      </p>

      <div className="mt-4">
        <pre className="overflow-x-auto rounded border border-border bg-surface p-5 font-mono text-[12.5px] leading-6 text-dim">
          <code>
            {before}
            {"Use "}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="mx-1 inline-flex max-w-[320px] cursor-pointer items-center gap-1.5 rounded-md border border-brand-500/50 bg-brand-500/10 px-2.5 py-1 align-middle font-mono text-[12.5px] font-medium text-brand-600 shadow-sm transition-colors hover:border-brand-500 hover:bg-brand-500/20">
                  <KeyRound className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{keyLabel}</span>
                  <ChevronDown className="h-3.5 w-3.5 shrink-0" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                data-surface="developer"
                align="start"
                className="max-h-72 overflow-y-auto rounded border border-border bg-base"
              >
                {mintedKey && (
                  <DropdownMenuItem
                    onClick={() => setSelected("new")}
                    className="gap-2 font-mono text-[12.5px]"
                  >
                    <Check
                      className={cn("h-3.5 w-3.5", selected === "new" ? "" : "invisible")}
                    />
                    {mintedKey.name} (just minted)
                  </DropdownMenuItem>
                )}
                {(keys ?? []).map((k) => (
                  <DropdownMenuItem
                    key={k.id}
                    onClick={() => setSelected(k.id)}
                    className="gap-2 font-mono text-[12.5px]"
                  >
                    <Check
                      className={cn("h-3.5 w-3.5", selected === k.id ? "" : "invisible")}
                    />
                    {k.name}
                    {k.key_prefix && (
                      <span className="text-muted-foreground">
                        {k.key_prefix}…{k.key_suffix}
                      </span>
                    )}
                  </DropdownMenuItem>
                ))}
                {(mintedKey || (keys ?? []).length > 0) && <DropdownMenuSeparator />}
                <DropdownMenuItem
                  onClick={() => setMinting(true)}
                  className="gap-2 font-mono text-[12.5px] text-brand-600"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Create API key…
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            {keyTail}
            {after}
          </code>
        </pre>
      </div>

      {selectedKey && !usingMinted && (
        <p className="mt-2 max-w-2xl text-[12.5px] leading-5 text-muted-foreground">
          <span className="font-medium text-foreground">Heads up:</span> Stash never stores
          key secrets, so an existing key can&apos;t be embedded here — this prompt names{" "}
          <span className="font-mono">{selectedKey.name}</span> and expects it in your
          app&apos;s env. Want the key carried inside the prompt? Pick{" "}
          <button
            onClick={() => setMinting(true)}
            className="font-medium text-brand-600 underline underline-offset-2 hover:text-brand-500"
          >
            Create API key
          </button>{" "}
          in the chip instead.
        </p>
      )}

      <MintKeyDialog
        open={minting}
        onOpenChange={setMinting}
        onMinted={() => {}}
        onMintedKey={(key) => {
          setMintedKey(key);
          setSelected("new");
        }}
      />
    </section>
  );
}

/** Collapsed by default: most developers never need what's inside. */
function Advanced({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-t border-border pt-8">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronRight className={cn("h-3 w-3 transition-transform", open && "rotate-90")} />
        Advanced
      </button>
      {open && <div className="mt-6">{children}</div>}
    </div>
  );
}

function PromptSection({
  title,
  blurb,
  prompt,
}: {
  title: string;
  blurb: string;
  prompt: string;
}) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className="mb-12">
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading>{title}</SectionHeading>
        <button
          onClick={copy}
          className="flex shrink-0 items-center gap-2 rounded-sm bg-brand-500 px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-600"
        >
          <Copy className="h-3.5 w-3.5" />
          {copied ? "Copied" : "Copy prompt"}
        </button>
      </div>
      <p className="mt-2 max-w-2xl text-[13.5px] leading-6 text-muted-foreground">{blurb}</p>
      <div className="mt-4">
        <CodeBlock>{prompt}</CodeBlock>
      </div>
    </section>
  );
}
