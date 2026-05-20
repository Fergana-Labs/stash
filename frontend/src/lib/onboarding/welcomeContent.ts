// Generates the welcome HTML that gets dropped into workspace.description
// on first onboarding completion. The DescriptionEditor (Tiptap) accepts
// standard HTML, so we author plain strings.
//
// Design intent: this is a *starter doc the user will delete*. Concise,
// no marketing fluff, useful pointers grouped by what the user might
// want to try next.

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
};

export function generateWelcomeHtml(inputs: WelcomeInputs): string {
  const { path, source, displayName, inviteLink, sharedUrl, counts } = inputs;

  const parts: string[] = [];

  parts.push(
    `<h1>Welcome to your workspace, ${escapeHtml(displayName)}</h1>`,
  );
  parts.push(
    `<p>This is your About page. It&rsquo;s editable like any other doc — keep what&rsquo;s useful, delete the rest.</p>`,
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

  // Three things to try next — universal regardless of path.
  parts.push(`<h2>Three things to try next</h2>`);
  parts.push(
    `<ul>
      <li><strong><a href="/discover">Discover &amp; install Stashes</a></strong> — browse what others have published; copy any of them into your workspace as a starting point.</li>
      <li><strong>Invite a teammate</strong>${
        inviteLink
          ? ` — share <a href="${escapeAttr(inviteLink)}">${escapeHtml(inviteLink)}</a> with anyone you want in. Two cursors on the same markdown page is a real thing here.`
          : ` from workspace settings. Two cursors on the same markdown page is a real thing here.`
      }</li>
      <li><strong><a href="/onboarding?path=sharing">Share with a coding agent</a></strong> — point Claude Code / Cursor / Codex at the publish endpoint and let it produce shareable artifacts for you.</li>
    </ul>`,
  );

  // Compressed feature reference.
  parts.push(`<h2>What this product does</h2>`);
  parts.push(
    `<ul>
      <li>Imports from <strong>Notion, GitHub, Google Drive</strong>, plus agent transcripts and sessions.</li>
      <li>Real-time collaborative editing on every markdown page (two cursors at once).</li>
      <li>Ask questions about everything you&rsquo;ve imported — your agent is grounded on your stuff.</li>
      <li>Search across your full corpus.</li>
      <li>CLI &amp; coding-agent integrations for power users.</li>
    </ul>`,
  );

  parts.push(
    `<p><em>This page is just content — edit it, or delete it when you&rsquo;re done.</em></p>`,
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
