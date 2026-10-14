"use client";

import { CopyBlock, origin, snippets } from "./UseIt";

const USES = [
  ["Verify inside an agent loop", "Before an agent sends, merges or acts, it classifies its own output and retries or asks you when the intuition objects or isn't sure."],
  ["Monitor production", "Classify live traffic. Low-confidence decisions land in the Inbox; topics show where it's overruled most."],
  ["Regression tests for evals", "Pin the cases that must never break. Each new version reports what it fixed and broke, and can't ship if a pinned case fails."],
  ["Prompt optimization", "Use the calibrated probability of a good label as the score to maximize when searching prompts."],
  ["Post-training rewards", "The same probabilities make a smooth reward signal for RL or preference tuning, aligned to your judgment instead of a generic grader."],
  ["Routing and triage", "Send each input to the right queue, person or model, with a confidence you can act on."],
];

const PARTS = [
  ["The brief", "What you decide, what each label means and where its boundary is, which mistake is worse, and what it must never get wrong. It is written into the instructions Jev reads."],
  ["Criteria", "Observable yes/no or multiple-choice questions about the input (“Does it promise a refund outside policy?”). Jev answers each with a probability; these become the features."],
  ["Jev, asked directly", "Jev also answers the task itself zero-shot (for multi-issue: one yes/no per issue). With no labels, the intuition is exactly that answer."],
  ["Your labels", "A small calibrated model learns how much to trust each answer, starting from “trust Jev” and moving only as far as your labels justify — so 6–10 labels already help. A probe over embeddings adds what your examples look like beyond the criteria."],
  ["Honest measurement", "About 30% of labels are held out and never trained on. Agreement is measured there, with its sample size; Jev alone is the baseline."],
  ["Improving", "Corrections from the Inbox join the golden set with your reasons, reasons suggest new criteria, and training again produces a new version that's checked against pinned cases before it can ship."],
];

/** What intuitions are for, how they work, and how to call them. */
export default function HowItWorks({ id, name }: { id: string | null; name: string }) {
  const s = snippets(id ?? "<intuition id>", name);
  const base = origin();
  return (
    <div className="flex flex-col gap-6 text-[13px] leading-relaxed">
      <section>
        <h3 className="m-0 text-[15px] font-semibold">An intuition is your judgment, as a classifier</h3>
        <p className="m-0 mt-1 max-w-2xl text-muted-foreground">Describe a judgment call, label a handful of examples, and get a calibrated classifier that decides the way you would — one label, any set of issues, or good vs. bad — with an honest measure of how often it agrees with you. Nothing is fine-tuned: it wraps a judge model with your criteria, your labels and a small learned layer, so it trains in seconds and keeps learning from corrections.</p>
      </section>

      <section>
        <h3 className="m-0 mb-2 text-[14px] font-semibold">What to use it for</h3>
        <div className="grid gap-2 sm:grid-cols-2">
          {USES.map(([title, body]) => <div key={title} className="rounded-lg border border-border p-3"><div className="font-medium">{title}</div><p className="m-0 mt-0.5 text-[12.5px] text-muted-foreground">{body}</p></div>)}
        </div>
      </section>

      <section>
        <h3 className="m-0 mb-2 text-[14px] font-semibold">How it works</h3>
        <ol className="m-0 space-y-2 pl-5">
          {PARTS.map(([title, body]) => <li key={title}><b>{title}.</b> <span className="text-muted-foreground">{body}</span></li>)}
        </ol>
      </section>

      <section className="space-y-3">
        <h3 className="m-0 text-[14px] font-semibold">Connect</h3>
        <div className="space-y-1.5"><div className="font-medium">From a coding agent</div><CopyBlock label="agent prompt" text={s.agent} /></div>
        <div className="space-y-1.5">
          <div className="font-medium">MCP <span className="font-normal text-muted-foreground">— streamable HTTP at <code className="text-[12px]">{base}/mcp/intuitions</code></span></div>
          <CopyBlock label="MCP config" text={s.mcp} />
          <p className="m-0 text-[12px] text-muted-foreground">Tools: <code className="text-[11.5px]">list_intuitions, create_intuition, get_intuition, save_brief, add_examples, generate_examples, list_examples, label_example, accept_suggestions, propose_criteria, set_criteria, train, ship, classify, inbox, review_prediction, give_feedback</code>. Agents can build intuitions end to end; suggested labels still need a person to confirm them.</p>
        </div>
        <div className="space-y-1.5"><div className="font-medium">REST</div><CopyBlock label="curl" text={s.rest} /></div>
        <table className="w-full text-left text-[12px]">
          <thead className="text-muted-foreground"><tr className="[&>th]:py-1 [&>th]:pr-3 [&>th]:font-medium"><th>Endpoint</th><th>What it does</th></tr></thead>
          <tbody className="[&>tr]:border-t [&>tr]:border-border [&_td]:py-1.5 [&_td]:pr-3 [&_td:first-child]:font-mono [&_td:first-child]:text-[11px]">
            <tr><td>POST /api/v1/intuitions/{"{id}"}/predict</td><td>Classify one input (live version; add <code>&quot;version&quot;: &quot;draft&quot;</code> to test)</td></tr>
            <tr><td>POST /api/v1/intuitions/{"{id}"}/feedback</td><td>Record what actually happened, by prediction_id or your ref</td></tr>
            <tr><td>POST /api/v1/intuitions/{"{id}"}/examples</td><td>Add examples (labeled or not; multi labels join issues with +)</td></tr>
            <tr><td>POST /api/v1/intuitions/{"{id}"}/examples/generate</td><td>Draft borderline examples with suggested labels</td></tr>
            <tr><td>POST /api/v1/model-wizard/models/{"{id}"}/train</td><td>Train and get the held-out report</td></tr>
            <tr><td>POST /api/v1/intuitions/{"{id}"}/draft/promote</td><td>Ship the trained version</td></tr>
            <tr><td>GET /api/v1/model-wizard/models/{"{id}"}/queue/all</td><td>The inbox: decisions waiting for review</td></tr>
          </tbody>
        </table>
        <p className="m-0 text-[12px] text-muted-foreground">Authenticate with <code>Authorization: Bearer &lt;Stash API key&gt;</code>. The agent skill lives at <code>docs/skills/intuitions/SKILL.md</code>.</p>
      </section>
    </div>
  );
}
