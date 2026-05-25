import CopyButton from "./CopyButton";

const DEMO_PROMPT = `Run the Stash landing demo:

curl -s https://api.joinstash.ai/api/v1/demo/start

The response is markdown instructions. Read them in full and follow them exactly: qualify me with a few quick questions, author a personalized HTML slide deck about Stash, and publish everything as a public Stash link.

When you're done, print the link.`;

// Genspark-style chat input. Soft rounded card, generous padding, the
// prompt sits as body text (not a terminal slab), a single circular
// brand button copies it. No internal dividers, no eyebrow header — the
// whole card reads as one cohesive input the visitor knows how to
// interact with from every other AI product.
export default function LiveDemo() {
  return (
    <div className="w-full max-w-[680px]">
      <div className="rounded-2xl border border-border bg-surface px-5 pb-3 pt-5 shadow-[0_1px_3px_rgba(15,23,42,0.04),0_24px_48px_-24px_rgba(15,23,42,0.18)]">
        <div className="max-h-[7.2em] overflow-y-auto whitespace-pre-wrap break-words text-[15px] leading-[1.55] text-ink">
          {DEMO_PROMPT}
        </div>

        <div className="mt-3 flex items-center justify-between gap-3">
          <span className="text-[12.5px] text-dim">
            A demo to try in your coding agent.
          </span>
          <CopyButton
            value={DEMO_PROMPT}
            label="Copy"
            copiedLabel="Copied ✓"
            className="inline-flex h-9 items-center gap-1.5 rounded-full bg-ink px-3.5 text-[13px] font-medium text-white transition hover:bg-brand"
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
