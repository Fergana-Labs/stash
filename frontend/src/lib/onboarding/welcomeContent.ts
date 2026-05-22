// Generates the welcome HTML that gets dropped into workspace.description
// on first onboarding completion. The DescriptionEditor (Tiptap) accepts
// standard HTML, so we author plain strings.
//
// Design intent: a starter doc the user can keep or delete. Concise.

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

  parts.push(`<h2>What to try next</h2>`);
  parts.push(
    `<ul>
      <li><strong><a href="/onboarding?path=migrant">Import your existing data</a></strong> — Notion, GitHub, Obsidian, Google Drive.</li>
      <li><strong><a href="/discover">Discover &amp; install Stashes</a></strong> — browse skills and knowledge others have published; copy into this workspace.</li>
      <li><strong>Invite a teammate to this workspace</strong>${
        inviteLink
          ? ` — share <a href="${escapeAttr(inviteLink)}">${escapeHtml(inviteLink)}</a>.`
          : ` from workspace settings.`
      }</li>
      <li><strong>Install the CLI</strong> — let your coding agent use Stash directly: <code>pip install stashai</code></li>
    </ul>`,
  );

  parts.push(`<h2>How Stash works</h2>`);
  parts.push(
    `<p>Everything is organized within a <strong>Workspace</strong>. This is a shared hopper for everything agents produce or consume: session transcripts, HTML pages, markdown docs, images, tables, raw files. Structured or not. Within it, there are three main structures:</p>
    <ul>
      <li><strong>Stashes</strong> — virtual sub-workspaces. Bundle any subset of workspace data into a Stash; share to the public or make it private to everyone else in the workspace. This becomes the go-to point for teams, workstreams, or projects (e.g. LinkedIn marketing, Backend infra team, Kernel optimization reading group).</li>
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
