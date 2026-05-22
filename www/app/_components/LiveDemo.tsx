import CopyButton from "./CopyButton";

const DEMO_PROMPT = `Run the Stash landing demo:

curl -s https://api.joinstash.ai/api/v1/demo/start

The response is markdown instructions. Read them in full and follow them exactly: run a short Q&A with me, author a personalized HTML slide deck about Stash, and publish everything as a public Stash link.

When you're done, print the link.`;

const STEPS = [
  {
    eyebrow: "1",
    title: "Paste, hit enter",
    body: "One prompt into Claude Code, Cursor, Codex, Aider — anything you already drive with a chat agent.",
  },
  {
    eyebrow: "2",
    title: "Four questions",
    body: "The agent fetches our instructions, asks who you are and what your team works on, and grounds the deck in your situation.",
  },
  {
    eyebrow: "3",
    title: "Public link",
    body: "Your personalized slide deck, the Q&A session, and our knowledge base — bundled into a Stash you can share with one URL.",
  },
];

export default function LiveDemo() {
  return (
    <section
      id="try-it"
      className="border-b border-border-subtle bg-surface py-24 md:py-28"
    >
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="grid grid-cols-1 gap-12 md:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] md:items-center md:gap-16">
          <div>
            <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
              <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
              Try it in 90 seconds
            </p>
            <h2 className="mt-4 font-display text-[clamp(28px,3.6vw,46px)] font-bold leading-[1.05] tracking-[-0.025em] text-ink">
              One prompt into your coding agent.
              <br />
              <span className="text-brand">Walks out with a Stash.</span>
            </h2>
            <p className="mt-5 max-w-[500px] text-[16px] leading-[1.6] text-foreground">
              Paste this into the agent you already use. It interviews you for
              30 seconds, builds a personalized HTML slide deck about Stash,
              and publishes the deck, the Q&amp;A session, and our knowledge
              base as a single public Stash URL.
            </p>
            <p className="mt-3 max-w-[500px] text-[14.5px] leading-[1.55] text-dim">
              No signup, no install. The link is public-but-unlisted — only
              the people you share it with can see it.
            </p>

            <ul className="mt-9 space-y-4">
              {STEPS.map((step) => (
                <li key={step.eyebrow} className="flex gap-4">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-background font-mono text-[12.5px] font-semibold text-ink">
                    {step.eyebrow}
                  </span>
                  <div>
                    <p className="text-[14.5px] font-semibold text-ink">
                      {step.title}
                    </p>
                    <p className="mt-0.5 text-[14px] leading-[1.55] text-foreground">
                      {step.body}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div
            className="overflow-hidden rounded-[14px] border border-white/5 bg-inverted"
            style={{ boxShadow: "var(--shadow-terminal)" }}
          >
            <div className="flex items-center justify-between border-b border-white/5 px-3.5 py-2.5">
              <div className="flex items-center gap-3">
                <div className="flex gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                  <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                  <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                </div>
                <span className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-on-inverted-dim">
                  agent · paste anywhere
                </span>
              </div>
              <CopyButton
                value={DEMO_PROMPT}
                label="Copy prompt"
                copiedLabel="Copied ✓"
                className="inline-flex h-7 items-center rounded-md bg-brand px-3 text-[11.5px] font-medium text-white transition hover:bg-brand-hover"
              />
            </div>
            <pre className="max-h-[420px] overflow-y-auto whitespace-pre-wrap px-5 py-6 font-mono text-[13px] leading-[1.7] text-on-inverted">
              {DEMO_PROMPT}
            </pre>
          </div>
        </div>
      </div>
    </section>
  );
}
