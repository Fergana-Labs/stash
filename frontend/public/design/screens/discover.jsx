// Screen: Discover — public stashes from across stash.ai
const DISCOVER_STASHES = [
  { name: 'How Replicant ships agent infra', org: 'replicant.dev', cover: 'cover-2', items: 22, views: 184, owner: 'Tim @ Replicant',
    desc: 'A deep look at the planner-runner split, plus how Replicant runs evals against every PR.', trending: true },
  { name: 'Cursor — composer redesign teardown', org: 'cursor-eng', cover: 'cover-3', items: 12, views: 932, owner: 'Lee @ Cursor',
    desc: 'Annotated screen-by-screen breakdown of why the new composer is structured around plans, not chats.', trending: true },
  { name: 'Linear product OS — Q2 plan', org: 'linear-co', cover: 'cover-1', items: 18, views: 4280, owner: 'Tuomas @ Linear',
    desc: 'Public Q2 plan: focused projects, agent integrations, and where dashboards finally fit in.' },
  { name: 'Raycast extensions — agent loop', org: 'raycast', cover: 'cover-5', items: 7, views: 612, owner: 'Marin @ Raycast',
    desc: 'Three sessions on how Raycast got their extensions to chain into a longer agent loop without a runtime rewrite.' },
  { name: 'Pico AI — eval harness benchmarks', org: 'pico-ai', cover: 'cover-4', items: 9, views: 281, owner: 'Anjali @ Pico',
    desc: 'Their internal eval harness, benchmarks against five frontier models, and a frank post-mortem.' },
  { name: 'Open-source agent runtimes (compared)', org: 'agentcraft', cover: 'cover-6', items: 31, views: 1102, owner: 'Sasha @ AgentCraft',
    desc: 'Sasha\'s 31-page comparison of nine OSS agent runtimes — long-running, with weekly updates.' },
  { name: 'The MCP spec, annotated', org: 'mcp-wiki', cover: 'cover-3', items: 14, views: 5602, owner: 'mcp-wiki collab',
    desc: 'A community-maintained annotation of the Model Context Protocol with examples, edge cases, and gotchas.' },
  { name: 'Inside a 4-person agent team', org: 'fragments-lab', cover: 'cover-2', items: 16, views: 388, owner: 'Mira @ Fragments',
    desc: 'A week in the life of a tiny agent-tools team. Sessions, plans, retros — all public.' },
  { name: 'How we wrote our PRD with claude', org: 'ferganalabs', cover: 'cover-1', items: 8, views: 92, owner: 'Aiyana @ Fergana',
    desc: 'The exact sessions and pages that went into our PRD. Forked from /v0 launch prep.', own: true },
];

function DiscoverStashCard({ s }) {
  return (
    <a className="card" style={{
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
      minHeight: 280, cursor: 'pointer',
    }}>
      <div className={s.cover} style={{ height: 96, position: 'relative' }}>
        {s.trending && (
          <span style={{
            position: 'absolute', top: 10, left: 12,
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '2px 8px', borderRadius: 999, fontSize: 10.5,
            background: 'rgba(0,0,0,0.78)', color: '#fff',
            fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.04em',
          }}>↗ trending</span>
        )}
        {s.own && (
          <span style={{
            position: 'absolute', top: 10, left: 12,
            padding: '2px 8px', borderRadius: 999, fontSize: 10.5,
            background: 'rgba(255,255,255,0.92)', color: 'var(--brand-700)',
            fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.04em',
            border: '1px solid var(--brand-200)',
          }}>your stash</span>
        )}
      </div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', flex: 1 }}>
        <h3 style={{
          fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 700,
          letterSpacing: '-0.015em', margin: 0,
        }}>{s.name}</h3>
        <p style={{
          marginTop: 8, fontSize: 12.5, lineHeight: 1.55, color: 'var(--text-dim)',
          display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>{s.desc}</p>
        <div className="sys-label" style={{ marginTop: 12, fontSize: 10.5 }}>
          {s.items} items · {s.views} views
        </div>
        <div style={{ flex: 1 }} />
        <div style={{
          marginTop: 14, paddingTop: 10, borderTop: '1px solid var(--border-subtle-color)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6,
          fontSize: 11.5, color: 'var(--text-muted)',
        }}>
          <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {s.owner} · <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>{s.org}</span>
          </span>
          <button className="btn btn-sm" style={{ flexShrink: 0 }}>
            <Icon name="Plus" /> Add
          </button>
        </div>
      </div>
    </a>
  );
}

function DiscoverScreen() {
  return (
    <AppShell breadcrumb={['Discover']} activeSection="discover">
      <div style={{ maxWidth: 1180, margin: '0 auto', padding: '36px 48px 80px' }}>
        {/* Hero */}
        <div style={{ borderBottom: '1px solid var(--border-subtle-color)', paddingBottom: 20 }}>
          <p className="sys-label">Discover</p>
          <h1 style={{
            fontFamily: 'var(--font-display)', fontSize: 44, fontWeight: 900,
            letterSpacing: '-0.025em', lineHeight: 1.05, margin: '12px 0 8px',
          }}>Public stashes, in the wild.</h1>
          <p style={{ fontSize: 14.5, color: 'var(--text-dim)', maxWidth: 720, margin: 0, lineHeight: 1.55 }}>
            Browse stashes that workspaces have published and shared to Discover. Add any of them to Fergana
            Labs with one click — it becomes an external stash you and your agents can search.
          </p>
        </div>

        {/* Controls */}
        <div style={{
          marginTop: 16, display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            border: '1px solid var(--border-color)', background: 'var(--bg-base)',
            padding: '6px 10px', borderRadius: 8, flex: 1, maxWidth: 460,
          }}>
            <span style={{ color: 'var(--text-muted)' }}><Icon name="Search" /></span>
            <input
              placeholder="Search public stashes…"
              style={{
                flex: 1, border: 'none', background: 'transparent', outline: 'none',
                fontSize: 13, fontFamily: 'var(--font-sans)', color: 'var(--text-primary)',
              }}
            />
          </div>
          <div style={{
            display: 'inline-flex', gap: 2, padding: 3,
            border: '1px solid var(--border-color)', borderRadius: 8, background: 'var(--bg-base)',
          }}>
            {['Trending', 'Newest', 'Most viewed'].map((t, i) => (
              <span key={t} style={{
                padding: '3px 10px', borderRadius: 5,
                fontSize: 12, fontWeight: i === 0 ? 600 : 400,
                color: i === 0 ? 'var(--text-primary)' : 'var(--text-muted)',
                background: i === 0 ? 'var(--bg-raised)' : 'transparent',
                cursor: 'pointer',
              }}>{t}</span>
            ))}
          </div>
          <span style={{ flex: 1 }} />
          <span className="sys-label" style={{ fontSize: 10.5 }}>{DISCOVER_STASHES.length} results</span>
        </div>

        {/* Topic chips */}
        <div style={{
          marginTop: 14, display: 'flex', flexWrap: 'wrap', gap: 6,
        }}>
          {['agents infra', 'design systems', 'evals', 'MCP', 'PRDs', 'launches', 'PMing with agents', 'cursor', 'eng / runtimes'].map((t, i) => (
            <span key={t} style={{
              padding: '3px 10px', borderRadius: 999,
              fontSize: 11.5, color: i === 0 ? 'var(--brand-700)' : 'var(--text-dim)',
              border: '1px solid ' + (i === 0 ? 'var(--brand-200)' : 'var(--border-color)'),
              background: i === 0 ? 'var(--brand-50)' : 'transparent',
              cursor: 'pointer',
            }}>{t}</span>
          ))}
        </div>

        {/* Grid */}
        <div style={{
          marginTop: 24,
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14,
        }}>
          {DISCOVER_STASHES.map((s, i) => <DiscoverStashCard key={i} s={s} />)}
        </div>
      </div>
    </AppShell>
  );
}

window.DiscoverScreen = DiscoverScreen;
