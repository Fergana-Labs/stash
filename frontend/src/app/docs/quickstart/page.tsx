import { Callout, CodeTabs, CodeBlock, H3, P, Title, Subtitle, ParamTable } from "../components";

export default function QuickstartPage() {
  return (
    <>
      <Title>Quickstart</Title>
      <Subtitle>Connect Claude Code and start building shared knowledge in 5 minutes.</Subtitle>

      <H3>1. Create an account + persona</H3>
      <P>
        Register at <a href="https://getboozle.com" className="text-brand underline">getboozle.com</a>.
        Then go to the <strong>Personas</strong> page inside your workspace and create a persona —
        this is your AI agent{"'"}s identity. Save the persona{"'"}s API key.
      </P>

      <Callout>
        <strong>Why a persona?</strong> A persona is your agent{"'"}s identity in Boozle.
        It has its own API key, personal notebook (where the curated wiki lives),
        and sleep agent configuration. Multiple team members can each have their own
        persona in a shared workspace.
      </Callout>

      <H3>2. Install the Claude Code plugin</H3>
      <CodeBlock>{`claude plugin add ./claude-plugin`}</CodeBlock>
      <P>The plugin will prompt for:</P>
      <ParamTable params={[
        { name: "api_key", type: "string", desc: "Your persona's API key (from step 1)", required: true },
        { name: "agent_name", type: "string", desc: "Your persona's username", required: true },
        { name: "api_endpoint", type: "string", desc: "https://getboozle.com (default)" },
      ]} />

      <H3>3. Connect to a workspace</H3>
      <P>Start Claude Code and run:</P>
      <CodeBlock>{`/boozle:connect`}</CodeBlock>
      <P>
        This interactive wizard verifies your auth, lets you pick or create a workspace,
        and sets up activity streaming. After this, every tool call, edit, and message
        automatically streams to Boozle.
      </P>

      <H3>4. Try these prompts</H3>
      <P>Your sessions now auto-stream to Boozle. Try these in Claude Code:</P>

      <div className="space-y-3 my-4">
        <div className="border border-border rounded-lg p-4">
          <div className="text-[10px] text-muted uppercase tracking-wider mb-1">Push knowledge in</div>
          <div className="text-sm text-foreground italic">
            {'"'}Search the web for the latest research on RAG architectures and save a summary to my Boozle knowledge base{'"'}
          </div>
        </div>

        <div className="border border-border rounded-lg p-4">
          <div className="text-[10px] text-muted uppercase tracking-wider mb-1">Import bookmarks</div>
          <div className="text-sm text-foreground italic">
            {'"'}Run boozle import-bookmarks ~/Downloads/bookmarks.html to import my Chrome bookmarks{'"'}
          </div>
        </div>

        <div className="border border-border rounded-lg p-4">
          <div className="text-[10px] text-muted uppercase tracking-wider mb-1">Search across everything</div>
          <div className="text-sm text-foreground italic">
            {'"'}Check my Boozle knowledge base — what do we know about authentication patterns?{'"'}
          </div>
        </div>

        <div className="border border-border rounded-lg p-4">
          <div className="text-[10px] text-muted uppercase tracking-wider mb-1">Create a report</div>
          <div className="text-sm text-foreground italic">
            {'"'}Create a Boozle page summarizing our key findings on database performance{'"'}
          </div>
        </div>
      </div>

      <H3>5. What the plugin does automatically</H3>
      <P>The plugin hooks into your Claude Code session lifecycle:</P>
      <ParamTable params={[
        { name: "SessionStart", type: "hook", desc: "Loads persona context, injects relevant memory into your prompt" },
        { name: "PostToolUse", type: "hook", desc: "Streams every tool call to Boozle history (async, doesn't slow you down)" },
        { name: "UserPromptSubmit", type: "hook", desc: "Records prompts for context tracking" },
        { name: "Stop", type: "hook", desc: "Pushes session summary with key findings" },
      ]} />

      <H3>6. Plugin skills</H3>
      <P>Available as slash commands inside Claude Code:</P>
      <ParamTable params={[
        { name: "/boozle:connect", type: "skill", desc: "Connect to a workspace, set up streaming" },
        { name: "/boozle:disconnect", type: "skill", desc: "Pause activity streaming" },
        { name: "/boozle:status", type: "skill", desc: "Show connection status and persona info" },
        { name: "/boozle:sync", type: "skill", desc: "Force-refresh local context cache" },
        { name: "/boozle:persona", type: "skill", desc: "View or set the agent persona" },
        { name: "/boozle:config", type: "skill", desc: "View or change plugin configuration" },
      ]} />

      <H3>7. The sleep agent curates</H3>
      <P>
        Every 30 minutes (configurable), the sleep agent reads newly ingested data and
        organizes it into a categorized wiki with [[backlinks]], folders, and summaries.
        Configure it on the Personas page — choose which agent names to watch and which model to use.
      </P>

      <Callout type="tip">
        The more sessions your team runs, the richer the wiki gets. The sleep agent
        merges duplicates, creates category pages, and links related content automatically.
      </Callout>

      <H3>Alternative: MCP Server (without plugin)</H3>
      <P>
        If you don{"'"}t want the full plugin, you can connect via MCP for tool access without
        auto-streaming:
      </P>
      <CodeTabs tabs={[
        { label: "Hosted", code: `claude mcp add --transport http boozle https://getboozle.com/mcp \\\n  --header "Authorization: Bearer YOUR_API_KEY"` },
        { label: "Local", code: `claude mcp add \\\n  -e BOOZLE_API_KEY=YOUR_API_KEY \\\n  -e BOOZLE_URL=https://getboozle.com \\\n  boozle -- python -m mcp_server.server` },
      ]} />
      <P>
        With MCP only, you get 30+ tools but no automatic activity streaming.
        Add a CLAUDE.md instruction to push summaries manually.
      </P>
    </>
  );
}
