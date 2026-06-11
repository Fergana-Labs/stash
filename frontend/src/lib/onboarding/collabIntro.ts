// The starter page seeded when a user picks the "just write with my agent"
// onboarding path. It's a real Markdown page in their Drive — editable and
// deletable — that doubles as an explainer for how the agent-native Drive works.
//
// The page embeds its own id and the user's API key so the agent prompt is a
// one-shot copy-paste: the agent installs the CLI, authenticates, and edits
// this exact page while the user watches.

export function generateCollabIntroMarkdown({
  displayName,
  pageId,
  apiKey,
}: {
  displayName: string;
  pageId: string;
  apiKey: string;
}): string {
  const name = displayName.trim() || "there";
  return `# Welcome to your agent-native Drive, ${name}

This is a real page in your Stash — start typing to make it yours, or delete it. Edits save automatically, and you and your agent can edit the same page at the same time (two cursors at once).

## See your agent edit this page — right now

Paste this into Claude Code, Codex, or Cursor — keep this tab open and watch the edit land live:

\`\`\`
Install the Stash CLI: bash -c "$(curl -fsSL https://joinstash.ai/install)"
Authenticate: export STASH_API_KEY=${apiKey}
Read this page: stash files read-page ${pageId}
Then append a short hello note at the bottom and save the full updated markdown with:
stash files edit-page ${pageId} --content "<full updated markdown>"
\`\`\`

## What people keep here

- **Analytics dashboards** — live HTML pages your agent regenerates as the numbers change.
- **Slide decks & presentations** — we ship skills for building these.
- **Markdown plans your agents work from** — task lists, specs, runbooks.
- **Research notes, meeting summaries, PRDs** — anything you and your agent write together.

## How your agent reaches it

Your whole Drive mounts as a virtual filesystem your agent can navigate and edit:

- **CLI** — \`bash -c "$(curl -fsSL https://joinstash.ai/install)"\`, then your coding agent can \`ls\`, \`find\`, and \`rg\` across everything.
- **MCP** — point Claude Code, Cursor, Codex, or OpenCode at the Stash MCP server and they read and write pages directly.
- **API** — the same surface over HTTP for anything custom.

## Share it

Share any folder, page, or file with a link, or give specific people access — so teammates and their agents work from the same docs.
`;
}
