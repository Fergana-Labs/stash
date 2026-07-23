import { Callout, Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

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

      <H3>1. Install the CLI and sign in</H3>
      <CodeBlock>{`uv tool install stashai
stash signin`}</CodeBlock>
      <P>
        <Code>stash signin</Code> opens your browser to create an account (or sign in) and
        hands the CLI a key automatically — nothing to copy. It then detects the coding
        agents installed on your machine — Claude Code, Cursor, Codex, OpenCode, Gemini
        CLI, Openclaw — and installs their hooks, so sessions start streaming to your
        Stash right away.
      </P>
      <Callout>
        On an unattended, browser-less machine (a CI runner, a headless box), use{" "}
        <Code>stash signin --api-key</Code> with a pre-minted key instead of the browser flow.
      </Callout>

      <H3>2. Try these commands</H3>
      <P>Use the CLI to interact with your Stash:</P>
      <div className="space-y-3 my-6">
        {PROMPTS.map((p) => (
          <div key={p.label} className="rounded-2xl border border-border bg-surface px-5 py-4">
            <div className="text-[11px] font-semibold text-muted uppercase tracking-[0.2em] mb-2">{p.label}</div>
            <div className="text-[15px] text-foreground italic leading-7">{p.prompt}</div>
          </div>
        ))}
      </div>

      <H3>3. Build your knowledge base</H3>
      <P>
        Sessions stream into searchable sessions. Promote useful outputs into pages, organize
        them with folders, and bundle related resources into{" "}
        <Code>Skills</Code> to share them.
      </P>
      <Callout>
        <strong>Agent names</strong> are just strings on session events that identify which agent produced them.
        You can use different agent names across your sessions to track which agent produced what.
      </Callout>
    </>
  );
}
