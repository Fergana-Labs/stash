import { CodeBlock, CodeTabs, H3, P, ParamTable, Title, Subtitle } from "../components";

export default function ConsumePage() {
  return (
    <>
      <Title>Consume</Title>
      <Subtitle>Getting data into Boozle. Zero-friction — data flows in automatically or with one command.</Subtitle>

      <H3>Import bookmarks</H3>
      <CodeBlock>{`boozle import-bookmarks bookmarks.html`}</CodeBlock>
      <P>
        Parses Chrome/Firefox bookmark exports. Scrapes each URL — articles via trafilatura,
        YouTube transcripts via youtube-transcript-api, PDF text via pymupdf. Stores each as a notebook page.
      </P>
      <ParamTable params={[
        { name: "--notebook", type: "string", desc: 'Notebook name (default: "Bookmarks")' },
        { name: "--skip-scrape", type: "flag", desc: "Import titles + URLs only, skip content extraction" },
        { name: "--dry-run", type: "flag", desc: "Preview without importing" },
        { name: "--delay", type: "float", desc: "Seconds between scrape requests (default: 0.5)" },
        { name: "--ws", type: "UUID", desc: "Workspace ID (uses personal notebook if omitted)" },
      ]} />

      <H3>Push events via API</H3>
      <CodeTabs tabs={[
        { label: "curl", code: `curl -X POST https://getboozle.com/api/v1/memory/{store_id}/events \\\n  -H "Authorization: Bearer $API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '{"agent_name":"my-agent","event_type":"tool_use","content":"..."}'` },
        { label: "CLI", code: 'boozle history push "Searched for auth best practices" --agent my-agent --type tool_use' },
        { label: "MCP", code: "// Claude Code calls automatically via MCP tools\npush_memory_event(workspace_id, store_id, ...)" },
      ]} />

      <H3>File uploads</H3>
      <P>
        Upload via the REST API, the + button in chat, or the Image button in the notebook editor.
        Stored in S3-compatible storage (Cloudflare R2, AWS S3, MinIO).
      </P>

      <H3>Tables</H3>
      <P>
        Create structured data with typed columns. Import CSV files. Optionally enable
        row embeddings for semantic search — configure which columns to embed in the
        table settings.
      </P>
    </>
  );
}
