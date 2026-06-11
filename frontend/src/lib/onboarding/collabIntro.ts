// The starter page seeded when a user picks the "just write with my agent"
// onboarding path. It's a real Markdown page in their Drive — editable and
// deletable — that doubles as an explainer for how the agent-native Drive works.

export function generateCollabIntroMarkdown(displayName: string): string {
  const name = displayName.trim() || "there";
  return `# Welcome to your agent-native Drive, ${name}

This is a real page in your Stash — start typing to make it yours, or delete it. Edits save automatically, and you and your agent can edit the same page at the same time (two cursors at once).

## What lives here

- **Markdown & HTML pages** — like this one. The formats your agent already reads and writes.
- **Files** — drop in PDFs, CSVs, images; your agent can open them too.
- **Agent session transcripts** — every conversation with your coding agent, pushed in automatically.

## How your agent reaches it

Your whole Drive mounts as a virtual filesystem your agent can navigate and edit:

- **CLI** — \`pip install stashai\`, then your coding agent can \`ls\`, \`find\`, and \`rg\` across everything.
- **MCP** — point Claude Code, Cursor, Codex, or OpenCode at the Stash MCP server and they read and write pages directly.
- **API** — the same surface over HTTP for anything custom.

## Share it

Bundle any set of pages into a Cartridge with a link, or share a folder with specific people — so teammates and their agents work from the same docs.
`;
}
