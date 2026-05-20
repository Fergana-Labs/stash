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

  // Session trace upload. Agent figures out its own transcript path and
  // identity — nothing for the user to edit.
  return `Upload your own current session transcript to Stash so I can share it.

The transcript is the .jsonl file for this session — Claude Code stores them at \`~/.claude/projects/<cwd-slug>/<session-id>.jsonl\`; Cursor, Codex, and others have similar paths. Use that path, the session id (the filename without .jsonl), and your agent name when running:

WORKSPACE_ID=\$(curl -sS ${apiUrl}/api/v1/workspaces/mine \\
  -H "Authorization: Bearer ${apiKey}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["workspaces"][0]["id"])')

curl -sS -X POST ${apiUrl}/api/v1/workspaces/\$WORKSPACE_ID/transcripts \\
  -H "Authorization: Bearer ${apiKey}" \\
  -F "file=@<your transcript path>" \\
  -F "session_id=<session id from filename>" \\
  -F "agent_name=<your agent, e.g. claude-code>"

Print the response.`;
}
