import { Callout, CodeBlock, CodeTabs, H3, P, Title, Subtitle } from "../components";

const TOOLS = [
  { cat: "Auth", tools: "register, whoami, update_profile" },
  { cat: "Workspaces", tools: "create, list, join, info, members" },
  { cat: "Notebooks", tools: "create, read, update, delete, backlinks, outlinks, page_graph, semantic_search_pages, auto_index" },
  { cat: "Files", tools: "upload, list, get_url, delete" },
  { cat: "Tables", tools: "full CRUD + configure_embeddings, backfill, semantic_search_rows" },
  { cat: "History", tools: "push_event, push_batch, query, search, query_history (LLM synthesis)" },
  { cat: "Search", tools: "universal_search across all resource types" },
  { cat: "Curation", tools: "curate (organize workspace data into wiki pages)" },
];

export default function MCPPage() {
  return (
    <>
      <Title>MCP Server</Title>
      <Subtitle>
        Tools via the Model Context Protocol. Any MCP-compatible AI agent can read and write
        to Octopus without the full plugin.
      </Subtitle>

      <H3>Connect Claude Code</H3>
      <P>
        The hosted option connects directly to getoctopus.com — no local Python needed.
        The local option runs the MCP server on your machine, which is useful for self-hosted instances.
      </P>
      <CodeTabs tabs={[
        {
          label: "Hosted (recommended)",
          code: `claude mcp add --transport http octopus https://getoctopus.com/mcp \\
  --header "Authorization: Bearer YOUR_API_KEY"`,
        },
        {
          label: "Local MCP server",
          code: `# Requires: pip install octopus
claude mcp add \\
  -e OCTOPUS_API_KEY=YOUR_API_KEY \\
  -e OCTOPUS_URL=https://getoctopus.com \\
  octopus -- python -m mcp_server.server`,
        },
      ]} />

      <Callout type="tip">
        For automatic session streaming (all tool calls recorded, memory injected at session start),
        use the <strong>full Claude Code plugin</strong> instead. MCP alone gives you tool access —
        not automatic streaming.
      </Callout>

      <H3>All tools by category</H3>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {TOOLS.map((c) => (
          <div key={c.cat} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground w-28 flex-shrink-0">{c.cat}</span>
            <span className="text-[13px] text-dim font-mono leading-relaxed">{c.tools}</span>
          </div>
        ))}
      </div>

      <H3>Pagination and filtering</H3>
      <P>
        All list tools support <code className="text-brand font-mono text-[13px]">limit</code> and{" "}
        <code className="text-brand font-mono text-[13px]">offset</code> for pagination.
        Resource-specific tools also accept <code className="text-brand font-mono text-[13px]">workspace_id</code> to
        scope results to a particular workspace.
      </P>

      <H3>Example: push a history event</H3>
      <CodeBlock>{`# From within a Claude Code session (via MCP)
push_memory_event(
  workspace_id="ws-uuid",
  store_id="store-uuid",
  agent_name="my-agent",
  event_type="tool_use",
  content="Searched documentation for rate limiting patterns"
)`}</CodeBlock>
    </>
  );
}
