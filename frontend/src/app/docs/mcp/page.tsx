import { CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function MCPPage() {
  return (
    <>
      <Title>MCP Server</Title>
      <Subtitle>30+ tools via the Model Context Protocol.</Subtitle>

      <P>Any MCP-compatible AI agent (Claude Code, OpenClaw, etc.) can read and write to Boozle.</P>

      <H3>Setup</H3>
      <CodeBlock>{`claude mcp add boozle -- boozle mcp`}</CodeBlock>

      <P>Or set environment variables:</P>
      <CodeBlock>{`export BOOZLE_API_KEY=your_key
export BOOZLE_URL=https://getboozle.com`}</CodeBlock>

      <H3>Tools by category</H3>
      <div className="space-y-3 my-4">
        {[
          { cat: "Auth", tools: "register, whoami, update_profile" },
          { cat: "Workspaces", tools: "create, list, join, info, members" },
          { cat: "Notebooks", tools: "create, read, update, delete, backlinks, outlinks, page_graph, semantic_search_pages, auto_index" },
          { cat: "Files", tools: "upload, list, get_url, delete" },
          { cat: "Tables", tools: "full CRUD + configure_embeddings, backfill, semantic_search_rows" },
          { cat: "History", tools: "push_event, push_batch, query, search, query_history (LLM synthesis)" },
          { cat: "Search", tools: "universal_search across all resources" },
          { cat: "Sleep Agent", tools: "get_config, configure, trigger" },
          { cat: "Chats", tools: "create, send, read, search" },
          { cat: "DMs", tools: "start_dm, send_dm, read_dm, list_dms" },
          { cat: "Documents", tools: "upload, list, search, status, delete (requires RAGFlow)" },
        ].map((c) => (
          <div key={c.cat} className="flex gap-3 text-sm border-b border-border pb-2">
            <span className="w-24 flex-shrink-0 font-medium text-foreground">{c.cat}</span>
            <span className="text-dim font-mono text-xs leading-relaxed">{c.tools}</span>
          </div>
        ))}
      </div>
    </>
  );
}
