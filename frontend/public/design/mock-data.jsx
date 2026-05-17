// Mock data for the Stash prototype
window.MOCK = {
  user: { name: 'Aiyana Choi', initials: 'AC', avClass: 'av-rose' },
  workspace: {
    name: 'Fergana Labs',
    members: [
      { name: 'Aiyana Choi', initials: 'AC', avClass: 'av-rose' },
      { name: 'Henry Patel', initials: 'HP', avClass: 'av-indigo' },
      { name: 'Mara Olsen', initials: 'MO', avClass: 'av-emerald' },
      { name: 'Dani Reyes', initials: 'DR', avClass: 'av-amber' },
      { name: 'Sam Wu', initials: 'SW', avClass: 'av-sky' },
      { name: 'Priya Kapoor', initials: 'PK', avClass: 'av-fuchsia' },
    ],
  },

  pinnedStashes: [
    { name: 'v0 launch prep', visibility: 'workspace', items: 14 },
    { name: 'Customer interviews · oct', visibility: 'workspace', items: 22 },
    { name: 'Eval harness rewrite', visibility: 'private', items: 9 },
    { name: 'Series A deck research', visibility: 'public', items: 31 },
  ],

  // Filesystem tree shown in sidebar
  tree: [
    {
      type: 'folder', name: 'product', open: true, children: [
        { type: 'page', name: 'PRD — Stash v0', ext: 'md' },
        { type: 'page', name: 'Open questions', ext: 'md' },
        { type: 'folder', name: 'interviews', open: true, children: [
          { type: 'page', name: 'Mara — Acme dev tools' },
          { type: 'page', name: 'Henry — Replicant infra' },
          { type: 'page', name: 'Priya — Granola pm' },
          { type: 'table', name: 'interview-themes.csv' },
        ]},
        { type: 'page', name: 'Naming brainstorm' },
      ]
    },
    {
      type: 'folder', name: 'engineering', open: true, children: [
        { type: 'page', name: 'ARCHITECTURE', ext: 'md' },
        { type: 'page', name: 'agent-runtime-notes', ext: 'md' },
        { type: 'html', name: 'session-replay mockup', ext: 'html' },
        { type: 'folder', name: 'spikes', children: [
          { type: 'page', name: 'tree-shape-experiments' },
        ]},
      ]
    },
    {
      type: 'folder', name: 'gtm', children: [
        { type: 'page', name: 'launch-list' },
        { type: 'page', name: 'pricing draft' },
      ]
    },
    { type: 'page', name: 'README' },
    { type: 'page', name: 'team' },
  ],

  // Sessions grouped by date then user — matches sidebar pattern in DESIGN
  sessionDays: [
    {
      label: 'Today · May 17',
      users: [
        {
          user: 'Henry', avClass: 'av-indigo',
          sessions: [
            { id: 'henry-codex-3148', title: 'Wire up Stash MCP cli surface', time: '14:22', agent: 'Codex · GPT-5.5 ultra' },
            { id: 'henry-claude-3147', title: 'Sketch session-detail page', time: '11:08', agent: 'Claude Code · Sonnet 5' },
          ]
        },
        {
          user: 'Aiyana', avClass: 'av-rose',
          sessions: [
            { id: 'aiyana-claude-3146', title: 'Stash homepage newsfeed v1', time: '10:31', agent: 'Claude Code · Sonnet 5' },
          ]
        },
      ]
    },
    {
      label: 'Yesterday · May 16',
      users: [
        {
          user: 'Mara', avClass: 'av-emerald',
          sessions: [
            { id: 'mara-codex-3140', title: 'CSV → table conversion path', time: '17:55', agent: 'Codex · GPT-5.5 high' },
            { id: 'mara-codex-3138', title: 'Eval harness rewrite', time: '16:01', agent: 'Codex · GPT-5.5 ultra' },
          ]
        },
        {
          user: 'Priya', avClass: 'av-fuchsia',
          sessions: [
            { id: 'priya-claude-3136', title: 'Customer interview synth', time: '13:44', agent: 'Claude Code · Sonnet 5' },
          ]
        },
      ]
    },
    {
      label: 'Thu · May 15',
      users: [
        {
          user: 'Sam', avClass: 'av-sky',
          sessions: [
            { id: 'sam-cursor-3122', title: 'Markdown editor — TipTap setup', time: '18:09', agent: 'Cursor · GPT-5.5 ultra' },
          ]
        },
      ]
    },
  ],

  // Newsfeed items for workspace home
  feed: [
    {
      kind: 'session-pinned',
      user: 'Henry', avClass: 'av-indigo',
      time: '12 min ago',
      title: 'Wire up Stash MCP cli surface',
      summary: 'Added stash mcp list-stashes, mcp create-page, mcp add-to-stash. Touched 7 files in /cli/mcp. 3 tests added.',
      meta: { agent: 'Codex · GPT-5.5 ultra', files: 7, turns: 31 },
      stashes: ['v0 launch prep'],
    },
    {
      kind: 'page-edited',
      user: 'Aiyana', avClass: 'av-rose',
      time: '38 min ago',
      title: 'PRD — Stash v0',
      summary: 'Resolved 4 open questions: privacy model, table-as-page, external stash semantics, sessions ordering.',
      meta: { folder: 'product' },
      stashes: ['v0 launch prep', 'Customer interviews · oct'],
    },
    {
      kind: 'stash-published',
      user: 'Mara', avClass: 'av-emerald',
      time: '2 h ago',
      title: 'Eval harness rewrite — week 1',
      summary: 'Published as a public stash. 9 sessions, 4 pages, 1 table.',
      meta: { visibility: 'public', items: 14 },
    },
    {
      kind: 'discover',
      time: '3 h ago',
      title: 'How Replicant ships agent infra (publicly)',
      summary: 'Replicant just dropped their full v3 launch stash — 22 sessions, deep-dive on their planner-runner split, plus a really pretty pricing doc.',
      meta: { source: 'replicant.dev workspace', items: 22, views: 184 },
    },
    {
      kind: 'session-added',
      user: 'Aiyana', avClass: 'av-rose',
      time: '4 h ago',
      title: 'Stash homepage newsfeed v1',
      summary: 'Cleaned up the recent-activity feed: collapsed multi-edit sessions, surfaced stash chips, added discover row.',
      meta: { agent: 'Claude Code · Sonnet 5', turns: 18 },
      stashes: ['v0 launch prep'],
    },
  ],
};
