export type ShareKind = "html" | "markdown" | "session";

const TOPIC_PLACEHOLDER = "<your topic — e.g. 'how our rate limiter works'>";

function publishCurl(apiKey: string, apiUrl: string, contentType: "html" | "markdown") {
  return `curl -sS -X POST ${apiUrl}/api/v1/publish \\
  -H "Authorization: Bearer ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d @- <<'EOF'
{
  "title": "<your title>",
  "content_type": "${contentType}",
  "content": "<your generated ${contentType === "html" ? "HTML" : "markdown"}>",
  "public_permission": "read"
}
EOF`;
}

export function buildPrompt(kind: ShareKind, apiKey: string, apiUrl: string): string {
  if (kind === "html") {
    return `Make an HTML page about ${TOPIC_PLACEHOLDER}. Make it information-dense, use SVG diagrams where they help, and optimize it to be read once.

When you're done, publish it to Stash and print the share URL by running:

${publishCurl(apiKey, apiUrl, "html")}`;
  }

  if (kind === "markdown") {
    return `Write a markdown research note about ${TOPIC_PLACEHOLDER}. Use clear headings, fenced code blocks where it helps, and aim for the kind of doc a teammate would skim once.

When you're done, publish it to Stash and print the share URL by running:

${publishCurl(apiKey, apiUrl, "markdown")}`;
  }

  // Session trace: upload the agent's own .jsonl transcript. Needs the
  // workspace id, so the prompt includes a one-line lookup.
  return `Upload your current session transcript to Stash as a shareable trace. Find your transcript file (typically ~/.claude/projects/<dir>/<session>.jsonl, or your CLI's equivalent), then:

WORKSPACE_ID=$(curl -sS ${apiUrl}/api/v1/workspaces/mine \\
  -H "Authorization: Bearer ${apiKey}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["workspaces"][0]["id"])')

curl -sS -X POST ${apiUrl}/api/v1/workspaces/$WORKSPACE_ID/transcripts \\
  -H "Authorization: Bearer ${apiKey}" \\
  -F "file=@<path-to-your-session.jsonl>" \\
  -F "session_id=<session-id>" \\
  -F "agent_name=claude-code"

Print the response so I can see the upload succeeded.`;
}
