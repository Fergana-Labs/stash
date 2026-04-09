import Link from "next/link";
import { Callout, CodeBlock, CodeTabs, H3, P, ParamTable, Title, Subtitle } from "../components";

const PROMPTS = [
  { label: "Push knowledge in", prompt: '"Search the web for the latest research on RAG architectures and save a summary to my Octopus knowledge base"' },
  { label: "Import bookmarks", prompt: '"Run octopus import-bookmarks ~/Downloads/bookmarks.html to import my Chrome bookmarks"' },
  { label: "Search across everything", prompt: '"Check my Octopus knowledge base — what do we know about authentication patterns?"' },
  { label: "Create a report", prompt: '"Create a Octopus page summarizing our key findings on database performance"' },
];

export default function QuickstartPage() {
  return (
    <>
      <Title>Quickstart</Title>
      <Subtitle>Connect Claude Code and start building shared knowledge in 5 minutes.</Subtitle>

      <H3>1. Create an account and a persona</H3>
      <P>
        Register at{" "}
        <a href="https://getboozle.com" className="text-brand underline underline-offset-2">
          getboozle.com
        </a>{" "}
        then go to the <strong>Personas</strong> page inside your workspace and create a persona.
        This is your AI agent's identity in Octopus — it has its own API key, personal notebook,
        and sleep agent configuration. Save the persona's API key.
      </P>
      <P>
        <strong>Prefer the CLI?</strong> Instead of the web UI, run{" "}
        <code className="text-brand font-mono text-[13px]">octopus setup</code> after installing{" "}
        <code className="text-brand font-mono text-[13px]">pip install octopus</code>. The
        interactive wizard covers account creation, workspace creation, and history store setup
        in one shot — then come back to step 2.
      </P>

      <Callout>
        <strong>Why a persona?</strong> A persona is the identity your agent operates under.
        Multiple team members can have separate personas in a shared workspace, each with its
        own curated wiki and agent name filter.
      </Callout>

      <H3>2. Install the Claude Code plugin</H3>
      <CodeBlock>{`claude plugin add ./claude-plugin`}</CodeBlock>
      <P>The plugin will prompt for three values:</P>
      <ParamTable params={[
        { name: "api_key", type: "string", desc: "Your persona's API key from step 1", required: true },
        { name: "agent_name", type: "string", desc: "Your persona's username", required: true },
        { name: "api_endpoint", type: "string", desc: "https://getboozle.com (default)" },
      ]} />

      <H3>3. Connect to a workspace</H3>
      <P>Start a Claude Code session and run:</P>
      <CodeBlock>{`/octopus:connect`}</CodeBlock>
      <P>
        The interactive wizard verifies your auth, lets you pick or create a workspace, and enables
        activity streaming. After this, every tool call, edit, and message automatically streams to Octopus.
      </P>

      <H3>4. Try these prompts</H3>
      <P>Your sessions now auto-stream. Paste any of these into Claude Code to see Octopus in action:</P>
      <div className="space-y-3 my-6">
        {PROMPTS.map((p) => (
          <div key={p.label} className="rounded-2xl border border-border bg-surface px-5 py-4">
            <div className="text-[11px] font-semibold text-muted uppercase tracking-[0.2em] mb-2">{p.label}</div>
            <div className="text-[15px] text-foreground italic leading-7">{p.prompt}</div>
          </div>
        ))}
      </div>

      <H3>5. What the plugin does automatically</H3>
      <P>The plugin hooks into Claude Code session lifecycle events:</P>
      <ParamTable params={[
        { name: "SessionStart", type: "hook", desc: "Loads persona context and injects relevant memory into your prompt" },
        { name: "PostToolUse", type: "hook", desc: "Streams every tool call to Octopus history asynchronously — doesn't slow you down" },
        { name: "UserPromptSubmit", type: "hook", desc: "Records prompts for context tracking" },
        { name: "Stop", type: "hook", desc: "Pushes a session summary with key findings" },
      ]} />

      <H3>6. Plugin slash commands</H3>
      <P>Available as slash commands inside Claude Code:</P>
      <ParamTable params={[
        { name: "/octopus:connect", type: "skill", desc: "Connect to a workspace and set up streaming" },
        { name: "/octopus:disconnect", type: "skill", desc: "Pause activity streaming" },
        { name: "/octopus:status", type: "skill", desc: "Show connection status and persona info" },
        { name: "/octopus:sync", type: "skill", desc: "Force-refresh local context cache" },
        { name: "/octopus:persona", type: "skill", desc: "View or set the agent persona" },
        { name: "/octopus:config", type: "skill", desc: "View or change plugin configuration" },
      ]} />

      <H3>7. The sleep agent curates in the background</H3>
      <P>
        Every 30 minutes (configurable), the sleep agent reads newly ingested data and organizes
        it into a categorized wiki with <code className="text-brand font-mono text-[13px]">[[backlinks]]</code>,
        folders, and summaries. Configure it on the Personas page — choose which agent names to
        watch and which Claude model to use.
      </P>
      <Callout type="tip">
        The more sessions your team runs, the richer the wiki gets. The sleep agent merges
        duplicates, creates category pages, and links related content automatically.
      </Callout>

      <H3>Alternative: MCP Server (no plugin required)</H3>
      <P>
        If you prefer not to use the full plugin, connect via MCP for tool access without
        automatic session streaming:
      </P>
      <CodeTabs tabs={[
        { label: "Hosted", code: `claude mcp add --transport http octopus https://getboozle.com/mcp \\\n  --header "Authorization: Bearer YOUR_API_KEY"` },
        { label: "Local", code: `claude mcp add \\\n  -e OCTOPUS_API_KEY=YOUR_API_KEY \\\n  -e OCTOPUS_URL=https://getboozle.com \\\n  octopus -- python -m mcp_server.server` },
      ]} />
      <P>
        With MCP only you get 30+ tools but no automatic activity streaming.
        See the{" "}
        <Link href="/docs/mcp" className="text-brand underline underline-offset-2">MCP reference</Link>
        {" "}for the full tool list.
      </P>
    </>
  );
}
