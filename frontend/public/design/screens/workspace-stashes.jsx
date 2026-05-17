// Screen: Workspace stashes list (all stashes in the workspace)
// Plus: Discover screen (public stashes feed)

const WS_STASHES = [
  { name: 'v0 launch prep', visibility: 'public', items: 14, sessions: 4, pages: 9, views: 184, owner: 'Aiyana', edited: '38m ago',
    desc: 'PRD, design explorations, customer interview synth, and the agent sessions that produced each one.', cover: 'cover-1' },
  { name: 'Customer interviews · oct', visibility: 'workspace', items: 22, sessions: 12, pages: 9, views: 84, owner: 'Priya', edited: '2h ago',
    desc: 'Every dev-tools interview from October with raw transcripts, the synth doc, and the themes table.', cover: 'cover-2' },
  { name: 'Eval harness rewrite', visibility: 'private', items: 9, sessions: 7, pages: 2, views: 12, owner: 'Mara', edited: '4h ago',
    desc: 'Private — only Mara + Henry. Sessions and notes for the eval framework rebuild.', cover: 'cover-3' },
  { name: 'Series A deck research', visibility: 'public', items: 31, sessions: 8, pages: 21, views: 1240, owner: 'Aiyana', edited: '1d ago',
    desc: 'Public competitive + market research stash. The 21 pages have been our top external referrer this month.', cover: 'cover-4' },
  { name: 'CLI / MCP work', visibility: 'private', items: 7, sessions: 6, pages: 1, views: 6, owner: 'Henry', edited: '1d ago',
    desc: 'CLI surface design + MCP wiring sessions. Private until we land tests.', cover: 'cover-5' },
  { name: 'Agent runtime — external', visibility: 'workspace', items: 18, sessions: 0, pages: 18, views: 312, owner: 'Replicant', edited: '3d ago',
    desc: 'Forked from replicant.dev / agent runtime stash. Reference material only.', cover: 'cover-6', external: true },
];

function VisDot({ vis }) {
  const c = vis === 'public' ? '#22C55E' : vis === 'private' ? '#9CA3AF' : 'var(--brand-500)';
  return <span style={{ width: 6, height: 6, borderRadius: 999, background: c, display: 'inline-block' }} />;
}

function StashCard({ s }) {
  return (
    <a className="card" style={{
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
      minHeight: 260, cursor: 'pointer',
    }}>
      <div className={s.cover} style={{ height: 84, position: 'relative' }}>
        {s.external && (
          <span style={{
            position: 'absolute', top: 10, left: 12,
            padding: '2px 8px', borderRadius: 999, fontSize: 10.5,
            background: 'rgba(255,255,255,0.7)', backdropFilter: 'blur(4px)',
            fontFamily: 'var(--font-mono)', color: 'var(--text-primary)',
            border: '1px solid rgba(255,255,255,0.5)',
          }}>EXTERNAL</span>
        )}
        <span style={{
          position: 'absolute', top: 10, right: 12,
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '2px 8px', borderRadius: 999, fontSize: 11,
          background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(4px)',
          color: 'var(--text-dim)', textTransform: 'capitalize',
        }}>
          <VisDot vis={s.visibility} />
          {s.visibility}
        </span>
      </div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', flex: 1 }}>
        <h3 style={{
          fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 700,
          letterSpacing: '-0.015em', margin: 0,
        }}>{s.name}</h3>
        <p style={{
          marginTop: 8, fontSize: 12.5, lineHeight: 1.55, color: 'var(--text-dim)',
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>{s.desc}</p>

        <div className="sys-label" style={{ marginTop: 10, fontSize: 10.5 }}>
          {s.items} items · {s.sessions} sessions · {s.pages} pages · {s.views} views
        </div>

        <div style={{ flex: 1 }} />
        <div style={{
          marginTop: 14, paddingTop: 10, borderTop: '1px solid var(--border-subtle-color)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          fontSize: 11.5, color: 'var(--text-muted)',
        }}>
          <span>by {s.owner}</span>
          <span style={{ fontFamily: 'var(--font-mono)' }}>{s.edited}</span>
        </div>
      </div>
    </a>
  );
}

function WorkspaceStashesScreen() {
  return (
    <AppShell breadcrumb={['Stashes']} activeSection="">
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '32px 48px 80px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 16 }}>
          <div>
            <p className="sys-label">All stashes in workspace</p>
            <h1 style={{
              fontFamily: 'var(--font-display)', fontSize: 34, fontWeight: 700,
              letterSpacing: '-0.02em', margin: '4px 0 4px',
            }}>Stashes</h1>
            <p style={{ fontSize: 13.5, color: 'var(--text-dim)', maxWidth: 620, margin: 0 }}>
              Stashes are how things get bundled and shared in Fergana Labs. Privacy lives here — every page and session in a stash takes that stash&apos;s permission level.
            </p>
          </div>
          <button className="btn btn-sm btn-primary">
            <Icon name="Plus" /> New stash
          </button>
        </div>

        {/* Toolbar */}
        <div style={{
          marginTop: 22, display: 'flex', alignItems: 'center', gap: 8,
          paddingBottom: 10, borderBottom: '1px solid var(--border-color)',
        }}>
          {['All', 'Workspace', 'Private', 'Public', 'External'].map((t, i) => (
            <button key={t}
              className={i === 0 ? '' : 'btn-ghost'}
              style={{
                background: i === 0 ? 'var(--bg-raised)' : 'transparent',
                border: 'none', padding: '4px 10px',
                fontSize: 12.5, fontWeight: i === 0 ? 600 : 400,
                borderRadius: 6, cursor: 'pointer',
                color: i === 0 ? 'var(--text-primary)' : 'var(--text-muted)',
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
              {t !== 'All' && <VisDot vis={t.toLowerCase()} />}
              {t}
              <span className="sys-label" style={{ fontSize: 10 }}>
                {t === 'All' ? '14' : t === 'Workspace' ? '6' : t === 'Private' ? '3' : t === 'Public' ? '4' : '1'}
              </span>
            </button>
          ))}
          <span style={{ flex: 1 }} />
          <button className="btn btn-sm">
            <span style={{ color: 'var(--text-muted)' }}>sort ·</span>
            <span style={{ fontWeight: 500 }}>edited</span>
            <Icon name="ChevDown" />
          </button>
        </div>

        {/* Grid */}
        <div style={{
          marginTop: 16,
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12,
        }}>
          {WS_STASHES.map((s, i) => <StashCard key={i} s={s} />)}
        </div>
      </div>
    </AppShell>
  );
}

window.WorkspaceStashesScreen = WorkspaceStashesScreen;
