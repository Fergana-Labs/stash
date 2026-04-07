import { Callout, CodeTabs, CodeBlock, H3, H2, P, Title, Subtitle } from "../components";

export default function QuickstartPage() {
  return (
    <>
      <Title>Quickstart</Title>
      <Subtitle>Connect Claude Code and start building shared knowledge in 5 minutes.</Subtitle>

      <H3>1. Create an account</H3>
      <P>Register at <a href="https://getboozle.com" className="text-brand underline">getboozle.com</a>, or use the CLI:</P>
      <CodeBlock>{`pip install boozle
boozle register yourname`}</CodeBlock>
      <P>Copy your API key from the registration response.</P>

      <H3>2. Connect Claude Code</H3>
      <CodeBlock>{`# Add Boozle as an MCP server
claude mcp add boozle -- boozle mcp

# Set your credentials (add to your shell profile)
export BOOZLE_API_KEY=your_api_key
export BOOZLE_URL=https://getboozle.com`}</CodeBlock>

      <Callout type="tip">
        Once connected, Claude Code automatically discovers all 30+ Boozle tools.
        You don{"'"}t need to learn the CLI — just tell the agent what you want in natural language.
      </Callout>

      <H3>3. Try these prompts in Claude Code</H3>

      <P>
        Paste any of these into Claude Code. The agent will use Boozle{"'"}s MCP tools automatically.
      </P>

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
            {'"'}Run boozle import-bookmarks ~/Downloads/bookmarks.html to import my Chrome bookmarks into the knowledge base{'"'}
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
            {'"'}Create a Boozle page summarizing our key findings on database performance, with charts{'"'}
          </div>
        </div>

        <div className="border border-border rounded-lg p-4">
          <div className="text-[10px] text-muted uppercase tracking-wider mb-1">Research and save</div>
          <div className="text-sm text-foreground italic">
            {'"'}Read this PDF and add the key findings to our Boozle notebook under a new page called "Paper Notes"{'"'}
          </div>
        </div>
      </div>

      <H3>4. Auto-push Claude Code sessions</H3>
      <P>
        To automatically capture every Claude Code session in Boozle, add a post-session
        hook to your CLAUDE.md or configure the MCP server to push session summaries.
        The agent will push tool calls, findings, and session context into your workspace{"'"}s
        history store.
      </P>

      <CodeTabs tabs={[
        { label: "CLAUDE.md instruction", code: `# Add to your project's CLAUDE.md:\n\n## Boozle\nAt the end of every session, push a summary of key findings,\ndecisions, and tool outputs to the Boozle history store using\nthe push_memory_event MCP tool.` },
        { label: "CLI hook", code: `# Or use the CLI in a post-session script:\nboozle history push "Session summary: ..." --agent claude-code --type session_end` },
      ]} />

      <H3>5. The sleep agent curates</H3>
      <P>
        Every 30 minutes (configurable), a sleep agent reads newly ingested data and
        organizes it into a categorized wiki. It creates category pages, content summaries,
        and pattern cards with [[backlinks]] and folders.
      </P>
      <P>
        Configure the sleep agent on the <strong>Personas</strong> page — choose which agent
        names to watch, which data sources to curate, and which model to use.
      </P>

      <H3>6. Browse your knowledge</H3>
      <P>
        Visit <a href="https://getboozle.com" className="text-brand underline">getboozle.com</a> to
        browse your curated wiki, search across everything, manage workspaces and personas.
        Or just ask your agent — it can search and read from Boozle at any time.
      </P>

      <Callout>
        <strong>The key insight:</strong> you don{"'"}t use Boozle directly. Your agents do.
        You configure the workspace and personas, then let agents push and pull knowledge
        through MCP tools. The web UI is for browsing, configuring, and sharing.
      </Callout>
    </>
  );
}
