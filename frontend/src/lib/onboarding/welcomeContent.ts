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
  parts.push(
    `<p><em>This is your About page. It&rsquo;s editable like any other doc — keep what&rsquo;s useful, delete the rest.</em></p>`,
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
    `<p>Everything is organized within a <strong>Workspace</strong>. This is a shared hopper for everything agents produce or consume: session transcripts, HTML pages, markdown docs, images, tables, raw files. Structured or not. Within it, there are three main structures:</p>
    <ul>
      <li><strong>Cartridges</strong> — virtual sub-workspaces. Bundle any subset of workspace data into a Cartridge; share to the public or make it private to everyone else in the workspace. This becomes the go-to point for teams, workstreams, or projects (e.g. LinkedIn marketing, Backend infra team, Kernel optimization reading group).</li>
      <li><strong>Files</strong> — a file system for documents (e.g. markdown, HTML, images, PDF, CSV). Built so agents can natively use it.</li>
      <li><strong>Sessions</strong> — history of conversations between users and agents. Automatically pushed from your agent of choice (e.g. Claude Code, Codex, Openclaw).</li>
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
