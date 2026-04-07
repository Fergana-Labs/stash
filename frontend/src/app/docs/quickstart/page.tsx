import { Callout, CodeTabs, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function QuickstartPage() {
  return (
    <>
      <Title>Quickstart</Title>
      <Subtitle>Connect your agents and start building shared knowledge.</Subtitle>

      <H3>1. Install the CLI</H3>
      <CodeBlock>{`pip install boozle
boozle register yourname`}</CodeBlock>

      <H3>2. Connect Claude Code</H3>
      <P>
        Add Boozle as an MCP server so every Claude Code session feeds into your knowledge base:
      </P>
      <CodeTabs tabs={[
        { label: "MCP Setup", code: "claude mcp add boozle -- boozle mcp" },
        { label: "Environment", code: "export BOOZLE_API_KEY=your_api_key\nexport BOOZLE_URL=https://getboozle.com" },
      ]} />

      <Callout>
        Once connected, Claude Code can read from and write to your shared memory during sessions.
        Tool calls, research findings, and session summaries accumulate as searchable knowledge.
      </Callout>

      <H3>3. Push data in</H3>
      <P>Anything can go into the knowledge base — agent sessions, bookmarks, PDFs, web articles:</P>
      <CodeTabs tabs={[
        { label: "CLI Push", code: 'boozle history push "Key finding: the auth system uses JWT with refresh tokens" --agent research-bot' },
        { label: "Import Bookmarks", code: "boozle import-bookmarks ~/Downloads/bookmarks.html" },
        { label: "MCP (in agent)", code: "// Agents call this automatically via MCP tools\npush_memory_event(workspace_id, store_id, ...)" },
      ]} />

      <H3>4. Search across everything</H3>
      <CodeBlock>{`boozle search "what do we know about authentication patterns?"`}</CodeBlock>
      <P>
        AI-powered synthesis across notebooks, tables, history, and documents.
        Works from the CLI, web UI, or via MCP tools inside agent sessions.
      </P>

      <H3>5. Let the sleep agent curate</H3>
      <P>
        The sleep agent runs periodically (default: every 30 minutes). It reads newly ingested
        data and organizes it into a categorized wiki with [[backlinks]], folders, and summaries.
        Configure it per-persona on the Personas page — choose which workspaces to watch,
        which agent names to filter by, and which model to use.
      </P>

      <Callout type="tip">
        The more data you push in, the better the wiki gets. Start by connecting Claude Code,
        then add bookmarks, research PDFs, and any other reference material your team uses.
      </Callout>

      <H3>Web UI</H3>
      <P>
        Sign up at <a href="https://getboozle.com" className="text-brand underline">getboozle.com</a> to
        browse your curated wiki, manage workspaces and personas, and search from the browser.
      </P>
    </>
  );
}
