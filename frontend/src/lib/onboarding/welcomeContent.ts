// Generates the welcome HTML that gets dropped into workspace.description
// on first onboarding completion. The DescriptionEditor (Tiptap) accepts
// standard HTML, so we author plain strings.
//
// Design intent: a starter doc the user can keep or delete. Concise.

export type WelcomeInputs = {
  displayName: string;
  inviteLink: string | null;
  counts: {
    pages: number;
    files: number;
    sessions: number;
  };
};

export function generateWelcomeHtml(inputs: WelcomeInputs): string {
  const { displayName, inviteLink, counts } = inputs;

  const parts: string[] = [];

  parts.push(
    `<h1>Welcome to Stash, ${escapeHtml(displayName)}</h1>`,
  );

  if (counts.sessions > 0) {
    parts.push(`<h2>What you just did</h2>`);
    parts.push(
      `<ul><li>You&rsquo;ve got <strong>${counts.sessions} ${pluralize(
        "session",
        counts.sessions,
      )}</strong> uploaded.</li></ul>`,
    );
  }

  parts.push(`<h2>What to try next</h2>`);
  parts.push(
    `<ul>
      <li><strong><a href="/settings/integrations">Connect a data source</a></strong> — GitHub, Google Drive, Notion, Slack, Granola. Your agent reads across everything you connect.</li>
      <li><strong><a href="/discover">Discover &amp; install Cartridges</a></strong> — browse skills and knowledge others have published; add them to your Stash.</li>
      <li><strong>Invite a teammate</strong>${
        inviteLink
          ? ` — share <a href="${escapeAttr(inviteLink)}">${escapeHtml(inviteLink)}</a>.`
          : ` from settings.`
      }</li>
      <li><strong>Install the CLI</strong> — let your coding agent use Stash directly: <code>pip install stashai</code></li>
    </ul>`,
  );

  parts.push(`<h2>How Stash works</h2>`);
  parts.push(
    `<p>Stash is built around <strong>sources</strong> your agents read and write, <strong>cartridges</strong> you share on top of them, and the <strong>agents</strong> you talk to over all of it.</p>
    <ul>
      <li><strong>Sources</strong> — everything your agents produce or consume, all searchable:
        <ul>
          <li><strong>Agent Sessions</strong> — the history of your agent conversations, automatically pushed in from Claude Code, Codex, and friends.</li>
          <li><strong>Files</strong> — a file system for documents (markdown, HTML, images, PDF, CSV, tables), plus connected sources like Notion, Google Drive, Slack, and GitHub. Built so agents can use it natively.</li>
        </ul>
      </li>
      <li><strong>Cartridges</strong> — curated bundles you share on top of your sources: pick any subset and publish it, or share it with specific people. The go-to surface for a team, workstream, or project.</li>
      <li><strong>Agents</strong> — talk to an agent grounded on everything above: search it, ask about it, and let your coding agents work against it.</li>
    </ul>`,
  );

  parts.push(`<h2>What this product does</h2>`);
  parts.push(
    `<ul>
      <li><strong>Real-time collaborative editing</strong> on every markdown page (two cursors at once).</li>
      <li>Remember everything, not just the pretty docs — automatically <strong>store and index your agent sessions</strong>.</li>
      <li><strong>Built for agents.</strong> Use what they&rsquo;re natively fluent in: markdown, HTML, and virtual filesystems.</li>
      <li><strong>Search and ask about everything</strong> you&rsquo;ve added — your agent is grounded on your stuff.</li>
      <li><strong>Sharing as a first-class feature.</strong> Share a deck with a client, or let your teams&rsquo; agents work together.</li>
    </ul>`,
  );

  return parts.join("");
}

function pluralize(noun: string, n: number): string {
  return n === 1 ? noun : `${noun}s`;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(s: string): string {
  return escapeHtml(s);
}
