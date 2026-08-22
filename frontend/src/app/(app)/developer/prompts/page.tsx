"use client";

import { useEffect, useState } from "react";
import { ChevronRight, Copy } from "lucide-react";

import { cn } from "@/lib/utils";

import DeveloperGate from "@/components/developer/DeveloperGate";
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
            <select
              value={hasKey ? selected : "mint"}
              onChange={(e) => {
                if (e.target.value === "mint") setMinting(true);
                else setSelected(e.target.value);
              }}
              className="mx-0.5 inline-block max-w-[280px] cursor-pointer rounded border border-border bg-base px-1.5 py-0.5 align-baseline font-mono text-[12px] text-brand-700 focus:border-brand-500 focus:outline-none"
            >
              {mintedKey && <option value="new">{mintedKey.name} (just minted)</option>}
              {(keys ?? []).map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name}
                  {k.key_prefix ? ` · ${k.key_prefix}…${k.key_suffix}` : ""}
                </option>
              ))}
              <option value="mint">＋ Create API key…</option>
            </select>
            {keyTail}
            {after}
          </code>
        </pre>
      </div>

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
