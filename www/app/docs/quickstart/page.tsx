import { Callout, CodeBlock, H3, P, Title, Subtitle } from "../components";

const PROMPTS = [
  { label: "Push knowledge in", prompt: '"Search the web for the latest research on RAG architectures and save a summary to my Stash knowledge base"' },
  { label: "Search across everything", prompt: '"Check my Stash knowledge base — what do we know about authentication patterns?"' },
  { label: "Create a report", prompt: '"Create a Stash page summarizing our key findings on database performance"' },
];

export default function QuickstartPage() {
  return (
    <>
      <Title>Quickstart</Title>
      <Subtitle>Install the CLI, connect your coding agent, and start building shared knowledge in 5 minutes.</Subtitle>

      <H3>1. Create an account</H3>
      <P>
        Register at{" "}
        <a href="https://joinstash.ai" className="text-brand underline underline-offset-2">
          joinstash.ai
        </a>{" "}
        and save your API key.
      </P>
      <P>
        <strong>Prefer the CLI?</strong> Instead of the web UI, run{" "}
        <code className="text-brand font-mono text-[13px]">stash connect</code> after installing{" "}
        <code className="text-brand font-mono text-[13px]">pip install stashai</code>. The
        interactive wizard covers account creation and workspace creation
        in one shot — then come back to step 2.
      </P>

      <Callout>
        <strong>Agent names</strong> are just strings on history events that identify which agent produced them.
        Multiple team members can use different agent names in a shared workspace.
      </Callout>

      <H3>2. Install the CLI</H3>
      <CodeBlock>{`pip install stashai
stash login`}</CodeBlock>

      <H3>3. Try these commands</H3>
      <P>Use the CLI to interact with your workspace:</P>
      <div className="space-y-3 my-6">
        {PROMPTS.map((p) => (
          <div key={p.label} className="rounded-2xl border border-border bg-surface px-5 py-4">
            <div className="text-[11px] font-semibold text-muted uppercase tracking-[0.2em] mb-2">{p.label}</div>
            <div className="text-[15px] text-foreground italic leading-7">{p.prompt}</div>
          </div>
        ))}
      </div>

      <H3>4. Curate your knowledge base</H3>
      <P>
        Curation runs automatically after agent sessions (with a 24-hour cooldown), organizing
        ingested data into a categorized wiki with <code className="text-brand font-mono text-[13px]">[[backlinks]]</code>,
        folders, and summaries. You can also trigger it manually with
        the <code className="text-brand font-mono text-[13px]">/curate</code> slash command in supported agents.
      </P>
      <Callout type="tip">
        The more data you push, the richer the wiki gets. The curation tool merges
        duplicates, creates category pages, and links related content automatically.
        Toggle auto-curation in <code className="text-brand font-mono text-[13px]">stash settings</code>.
      </Callout>
    </>
  );
}
