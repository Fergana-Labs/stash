import { AGENT_DOCS } from "../../_lib/agent-docs";

// Raw markdown for agents. The proxy's content negotiation rewrites
// curl-style GETs of /pages/agents here, same as it does for pastes.
export async function GET() {
  return new Response(AGENT_DOCS, {
    headers: { "Content-Type": "text/markdown; charset=utf-8" },
  });
}
