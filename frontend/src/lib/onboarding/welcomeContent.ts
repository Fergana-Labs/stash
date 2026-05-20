// Generates the welcome HTML that gets dropped into workspace.description
// on first onboarding completion. The DescriptionEditor (Tiptap) accepts
// standard HTML, so we author plain strings.
//
// Design intent: a starter doc the user will delete. Concise, no fluff.

import type { PathId, MigrantSource } from "./paths";

export type WelcomeInputs = {
  path: PathId | null;
  source: MigrantSource | null;
  displayName: string;
  inviteLink: string | null;
  sharedUrl: string | null;
  counts: {
    pages: number;
    files: number;
    sessions: number;
  };
};

const SOURCE_LABELS: Record<MigrantSource, string> = {
  notion: "Notion",
  obsidian: "Obsidian",
  github: "GitHub",
  drive: "Google Drive",
};

export function generateWelcomeHtml(inputs: WelcomeInputs): string {
  const { path, source, displayName, inviteLink, sharedUrl, counts } = inputs;

  const parts: string[] = [];

  parts.push(
    `<h1>Welcome to your workspace, ${escapeHtml(displayName)}</h1>`,
  );
  parts.push(
    `<p><em>This is your About page. It&rsquo;s editable like any other doc — keep what&rsquo;s useful, delete the rest.</em></p>`,
  );

  // What you just did — only show the bits that actually happened.
  const wrap: string[] = [];
  if (path === "migrant" && source) {
    const total = counts.pages + counts.files;
    if (total > 0) {
      wrap.push(
        `You imported <strong>${total} ${pluralize("item", total)}</strong> from ${SOURCE_LABELS[source]}.`,
      );
    } else {
      wrap.push(`Your ${SOURCE_LABELS[source]} import is running.`);
    }
  }
  if (path === "sharing" && sharedUrl) {
    wrap.push(
      `You published your first artifact — <a href="${escapeAttr(sharedUrl)}">${escapeHtml(sharedUrl)}</a>.`,
    );
  }
  if (path === "memory") {
    wrap.push(`You asked your first question. Your agent has memory now.`);
  }
  if (counts.sessions > 0) {
    wrap.push(
      `You&rsquo;ve got <strong>${counts.sessions} ${pluralize("session", counts.sessions)}</strong> uploaded.`,
    );
  }
  if (wrap.length > 0) {
    parts.push(`<h2>What you just did</h2>`);
    parts.push(`<ul>${wrap.map((w) => `<li>${w}</li>`).join("")}</ul>`);
  }

  // What to try next — imports lead, then Discover, invite, CLI.
  parts.push(`<h2>What to try next</h2>`);
  parts.push(
    `<ul>
      <li><strong><a href="/onboarding?path=migrant&amp;step=2&amp;source=notion">Import from Notion</a></strong> — pages, databases, and sub-pages.</li>
      <li><strong><a href="/onboarding?path=migrant&amp;step=2&amp;source=github">Import from GitHub</a></strong> — markdown becomes pages, everything else lands in Files.</li>
      <li><strong><a href="/onboarding?path=migrant&amp;step=2&amp;source=obsidian">Import from Obsidian</a></strong> — drop your vault folder; every note becomes a collaboratively-edited page.</li>
      <li><strong><a href="/onboarding?path=migrant&amp;step=2&amp;source=drive">Import from Google Drive</a></strong> — folders, Docs, Sheets.</li>
      <li><strong><a href="/discover">Discover &amp; install Stashes</a></strong> — browse what others have published; copy any of them into your workspace.</li>
      <li><strong>Invite a teammate</strong>${
        inviteLink
          ? ` — share <a href="${escapeAttr(inviteLink)}">${escapeHtml(inviteLink)}</a>. Two cursors on the same markdown page is a real thing here.`
          : ` from workspace settings.`
      }</li>
      <li><strong>Install the CLI</strong> — let your coding agent use Stash directly: <code>npm i -g @joinstash/cli</code></li>
    </ul>`,
  );

  // 3-layer mental model.
  parts.push(`<h2>How Stash works</h2>`);
  parts.push(
    `<p>Three layers, top down:</p>
    <ul>
      <li><strong>Data</strong> — a hopper for everything your agent produces or consumes: <code>.jsonl</code> session transcripts, HTML pages, markdown docs, images, tables, raw files. Structured or not.</li>
      <li><strong>Workspace</strong> — your private container. Everything you import or generate lands here; your agent reads from here.</li>
      <li><strong>Stashes</strong> — virtual sub-workspaces. Bundle any subset of your workspace data into a Stash; share it with a public link (view or edit), or invite teammates to your workspace.</li>
    </ul>`,
  );

  // Compressed feature reference.
  parts.push(`<h2>What this product does</h2>`);
  parts.push(
    `<ul>
      <li>Real-time collaborative editing on every markdown page (two cursors at once).</li>
      <li>Ask questions about everything you&rsquo;ve imported — your agent is grounded on your stuff.</li>
      <li>Search across your full corpus.</li>
      <li>CLI &amp; coding-agent integrations.</li>
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
