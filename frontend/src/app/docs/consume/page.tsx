import { Callout, CodeBlock, CodeTabs, H3, P, ParamTable, Title, Subtitle } from "../components";

export default function ConsumePage() {
  return (
    <>
      <Title>Consume</Title>
      <Subtitle>
        Getting data into Boozle. Agents push automatically via plugin or MCP. You can also
        import manually from the CLI or REST API.
      </Subtitle>

      <Callout type="tip">
        <strong>Auto-streaming</strong> is the default path. Once the Claude Code plugin is
        connected, every tool call and message flows into Boozle without any extra steps.
      </Callout>

      <H3>Import bookmarks</H3>
      <P>
        Export your Chrome or Firefox bookmarks as HTML, then import them in one command.
        Boozle scrapes each URL — articles via trafilatura, YouTube transcripts via
        youtube-transcript-api, PDF text via pymupdf — and stores each as a notebook page.
      </P>
      <CodeBlock>{`boozle import-bookmarks bookmarks.html`}</CodeBlock>
      <ParamTable params={[
        { name: "--notebook", type: "string", desc: 'Notebook name to write to (default: "Bookmarks")' },
        { name: "--skip-scrape", type: "flag", desc: "Import titles and URLs only — skip content extraction" },
        { name: "--dry-run", type: "flag", desc: "Preview what would be imported without writing anything" },
        { name: "--delay", type: "float", desc: "Seconds between scrape requests (default: 0.5)" },
        { name: "--ws", type: "UUID", desc: "Workspace ID — uses personal notebook if omitted" },
      ]} />

      <H3>Push events via the API</H3>
      <P>
        Any system that produces structured output can push events directly.
        Use the REST endpoint, the CLI shortcut, or let MCP handle it automatically.
      </P>
      <CodeTabs tabs={[
        {
          label: "curl",
          code: `curl -X POST https://getboozle.com/api/v1/workspaces/{ws}/memory/{store}/events \\
  -H "Authorization: Bearer $API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"agent_name":"my-agent","event_type":"tool_use","content":"..."}'`,
        },
        {
          label: "CLI",
          code: `boozle history push "Searched for auth best practices" \\
  --agent my-agent --type tool_use`,
        },
        {
          label: "MCP",
          code: `# Claude Code calls this automatically via the MCP tool
push_memory_event(workspace_id, store_id, ...)`,
        },
      ]} />

      <H3>File uploads</H3>
      <P>
        Upload images, PDFs, and documents through the REST API, via the + button in chat,
        or the image button in the notebook editor. Files are stored in S3-compatible storage
        (Cloudflare R2, AWS S3, or MinIO depending on your deployment).
      </P>

      <H3>Tables</H3>
      <P>
        Create structured data with typed columns (text, number, date, select, relation).
        Import CSV files directly. Optionally enable row embeddings for semantic search —
        configure which columns to use in the table settings panel.
      </P>
    </>
  );
}
