export type ShareKind = "html" | "markdown" | "session";

function publishCurl(apiKey: string, apiUrl: string, contentType: "html" | "markdown") {
  return `curl -sS -X POST ${apiUrl}/api/v1/publish \\
  -H "Authorization: Bearer ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d @- <<'EOF'
{
  "title": "<title>",
  "content_type": "${contentType}",
  "content": "<content>",
  "public_permission": "read"
}
EOF`;
}

export function buildPrompt(kind: ShareKind, apiKey: string, apiUrl: string): string {
  if (kind === "html") {
    return `Publish an HTML page to Stash. At the bottom of this prompt I'll give you either:

- a path to an existing .html file (read it and publish its contents as-is), or
- a topic (write a new information-dense HTML page about it — use SVG diagrams where they help)

Pick a short descriptive title. Replace <title> with that title and <content> with the HTML (escape any quotes for JSON). Run the curl and print the share URL it returns.

${publishCurl(apiKey, apiUrl, "html")}

---
INPUT: <edit this — either ./path/to/file.html, or a topic like "how our rate limiter works">`;
  }

  if (kind === "markdown") {
    return `Publish a markdown doc to Stash. At the bottom of this prompt I'll give you either:

- a path to an existing .md file (read it and publish its contents as-is), or
- a topic (write a new markdown research note about it — clear headings, fenced code blocks where they help)

Pick a short descriptive title. Replace <title> with that title and <content> with the markdown (escape any quotes for JSON). Run the curl and print the share URL it returns.

${publishCurl(apiKey, apiUrl, "markdown")}

---
INPUT: <edit this — either ./path/to/file.md, or a topic like "RFC: streaming token usage">`;
  }

  // Session trace upload. Workspace ID fetched at runtime; user only edits
  // the .jsonl path, session ID, and agent name at the bottom.
  return `Upload my current session transcript to Stash so I can share it. Substitute the values at the bottom of this prompt into the curl and run it. Print the response.

WORKSPACE_ID=\$(curl -sS ${apiUrl}/api/v1/workspaces/mine \\
  -H "Authorization: Bearer ${apiKey}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["workspaces"][0]["id"])')

curl -sS -X POST ${apiUrl}/api/v1/workspaces/\$WORKSPACE_ID/transcripts \\
  -H "Authorization: Bearer ${apiKey}" \\
  -F "file=@<transcript_path>" \\
  -F "session_id=<session_id>" \\
  -F "agent_name=<agent_name>"

---
TRANSCRIPT_PATH: <edit this — e.g. ~/.claude/projects/myproj/abc-123.jsonl>
SESSION_ID: <edit this — any unique id, e.g. session-2026-05-21>
AGENT_NAME: claude-code`;
}
