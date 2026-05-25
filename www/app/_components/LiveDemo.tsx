import CopyButton from "./CopyButton";

const DEMO_PROMPT = `Run the Stash landing demo:

curl -s https://api.joinstash.ai/api/v1/demo/start

The response is markdown instructions. Read them in full and follow them exactly: qualify me with a few quick questions, author a personalized HTML slide deck about Stash, and publish everything as a public Stash link.

When you're done, print the link.`;

// Chat-input-styled "try it" box that lives inside the hero. Mirrors the
// Manus/Genspark pattern: a prompt sits in a textarea-shaped container,
// a single primary action copies it ready for the user's coding agent.
export default function LiveDemo() {
  return (
    <div className="w-full max-w-[680px]">
      <div className="relative rounded-2xl border border-border bg-background shadow-[0_1px_3px_rgba(15,23,42,0.04),0_24px_48px_-24px_rgba(15,23,42,0.18)]">
        <div className="flex items-center gap-2 border-b border-border-subtle px-4 py-2.5">
          <span className="inline-flex h-1.5 w-1.5 rounded-full bg-brand" />
          <span className="font-mono text-[10.5px] font-medium uppercase tracking-[0.14em] text-muted">
            Try Stash now · paste into your agent
          </span>
        </div>

        <pre className="m-0 max-h-[1.7em] overflow-y-auto whitespace-pre-wrap break-words px-5 py-3 font-mono text-[13px] leading-[1.6] text-ink">
          {DEMO_PROMPT}
        </pre>

        <div className="flex items-center justify-end gap-3 border-t border-border-subtle px-4 py-2.5">
          <CopyButton
            value={DEMO_PROMPT}
            label="Copy prompt →"
            copiedLabel="Copied ✓"
            className="inline-flex h-8 items-center rounded-md bg-brand px-3.5 text-[12.5px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
          />
        </div>
      </div>
      <p className="mt-3 text-center text-[12.5px] text-dim">
        No signup. The agent asks you a few questions, builds you a deck,
        hands back a public Stash URL.
      </p>
    </div>
  );
}
