// Screen: Stash detail (public-facing-style, shown inside workspace)
// Mirrors the StashPageClient layout: workspace banner top + left rail nav + sections grouped.

function StashDetailScreen() {
  return (
    <AppShell
      breadcrumb={['Stashes', 'v0 launch prep']}
      activeSection=""
      activePage="v0 launch prep"
    >
      {/* Workspace strip */}
      <div style={{
        borderBottom: '1px solid var(--border-subtle-color)',
        background: 'var(--bg-surface)',
      }}>
        <div style={{
          maxWidth: 1180, margin: '0 auto', padding: '14px 28px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
        }}>
          <div style={{ minWidth: 0 }}>
            <p className="sys-label">Fergana Labs · workspace</p>
            <h1 style={{
              fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700,
              letterSpacing: '-0.015em', margin: '2px 0 0', display: 'flex', alignItems: 'center', gap: 10,
            }}>
              <span style={{ color: 'var(--brand-600)' }}><Icon name="Stash" /></span>
              v0 launch prep
              <span className="stash-chip public" style={{ marginLeft: 6 }}>
                <span className="dot" />public
              </span>
            </h1>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-sm">
              <Icon name="Users" /> Manage access
            </button>
            <button className="btn btn-sm">
              <Icon name="Download" /> Export
            </button>
            <button className="btn btn-sm btn-primary">
              <Icon name="Globe" /> Copy public link
            </button>
          </div>
        </div>
      </div>

      <div style={{
        maxWidth: 1180, margin: '0 auto', padding: '32px 28px 80px',
        display: 'grid', gridTemplateColumns: '200px minmax(0, 1fr)', gap: 32,
      }}>
        {/* Left rail */}
        <aside style={{ position: 'sticky', top: 12, alignSelf: 'flex-start' }}>
          <nav style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
            {[
              ['Home', true],
              ['Pages', false, 8],
              ['Sessions', false, 4],
              ['Tables', false, 1],
              ['Shared pages', false, 1],
            ].map(([t, active, count], i) => (
              <a key={i} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '6px 10px', borderRadius: 6,
                background: active ? 'var(--bg-raised)' : 'transparent',
                color: active ? 'var(--text-primary)' : 'var(--text-dim)',
                fontWeight: active ? 500 : 400,
                cursor: 'pointer',
              }}>
                <span style={{ flex: 1 }}>{t}</span>
                {count && <span className="sys-label" style={{ fontSize: 10 }}>{count}</span>}
              </a>
            ))}
          </nav>

          <div style={{ marginTop: 18, fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.7 }}>
            <div className="sys-label" style={{ marginBottom: 6 }}>About</div>
            <div>14 items</div>
            <div>184 views</div>
            <div>5 collaborators</div>
            <div>Created May 4</div>
            <div>by Aiyana Choi</div>
          </div>
        </aside>

        {/* Body */}
        <div style={{ minWidth: 0 }}>
          {/* Hero */}
          <div style={{ borderBottom: '1px solid var(--border-subtle-color)', paddingBottom: 28 }}>
            <p className="sys-label">Stash · 14 items · 184 views</p>
            <h2 style={{
              fontFamily: 'var(--font-display)', fontSize: 44, fontWeight: 900,
              letterSpacing: '-0.025em', lineHeight: 1.05, margin: '14px 0 0',
            }}>v0 launch prep</h2>

            <div className="card-soft" style={{
              padding: 18, maxWidth: 760, marginTop: 20,
            }}>
              <div className="sys-label">About this stash</div>
              <p style={{ marginTop: 8, fontSize: 14.5, lineHeight: 1.7, color: 'var(--text-primary)' }}>
                Everything we&apos;re using to ship Stash v0 — the PRD, the homepage spec, a half-dozen design
                explorations, the customer interview synth, and the agent sessions that produced each one.
                Hand this stash to a new teammate on day one.
              </p>
            </div>

            {/* Summary stats */}
            <div style={{ marginTop: 18, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
              {[
                ['Pages', 8, 'var(--text-primary)'],
                ['Sessions', 4, 'var(--agent)'],
                ['Tables', 1, '#16A34A'],
                ['Shared pages', 1, 'var(--brand-600)'],
              ].map(([t, v, c], i) => (
                <div key={i} className="card" style={{ padding: 12 }}>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 700, color: c, letterSpacing: '-0.02em' }}>{v}</div>
                  <div className="sys-label" style={{ marginTop: 2 }}>{t}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Pages section */}
          <StashSection title="Pages" count={8}>
            {[
              { icon: 'Page', name: 'PRD — Stash v0', sub: 'Page · markdown · in /product', kind: 'page' },
              { icon: 'Page', name: 'Open questions', sub: 'Page · markdown · in /product', kind: 'page' },
              { icon: 'Html', name: 'launch-narrative-v3.html', sub: 'Page · html · in /product', kind: 'html' },
              { icon: 'Page', name: 'ARCHITECTURE', sub: 'Page · markdown · in /engineering', kind: 'page' },
              { icon: 'Html', name: 'session-replay mockup', sub: 'Page · html · in /engineering', kind: 'html' },
              { icon: 'Page', name: 'launch-list', sub: 'Page · markdown · in /gtm', kind: 'page' },
              { icon: 'Page', name: 'pricing draft', sub: 'Page · markdown · in /gtm', kind: 'page' },
              { icon: 'Page', name: 'README', sub: 'Page · markdown · in /', kind: 'page' },
            ].map((it, i) => <StashItemRow key={i} it={it} />)}
          </StashSection>

          {/* Sessions section */}
          <StashSection title="Sessions" count={4}>
            {[
              { name: 'Wire up Stash MCP cli surface', sub: 'Today · Henry · 31 turns · Codex GPT-5.5 ultra' },
              { name: 'Stash homepage newsfeed v1', sub: 'Today · Aiyana · 18 turns · Claude Sonnet 5' },
              { name: 'Eval harness rewrite', sub: 'Yesterday · Mara · 42 turns · Codex GPT-5.5 ultra' },
              { name: 'Customer interview synth', sub: 'Yesterday · Priya · 24 turns · Claude Sonnet 5' },
            ].map((it, i) => (
              <a key={i} className="linkrow" style={{ padding: '10px 12px' }}>
                <span style={{ color: 'var(--agent)' }}><Icon name="Session" /></span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 600 }}>{it.name}</div>
                  <div className="sys-label" style={{ fontSize: 10.5, marginTop: 2, color: 'var(--text-muted)' }}>{it.sub}</div>
                </div>
                <span className="tag tag-agent">agent</span>
              </a>
            ))}
          </StashSection>

          {/* Tables */}
          <StashSection title="Tables" count={1}>
            <a className="linkrow" style={{ padding: '10px 12px' }}>
              <span style={{ color: '#16A34A' }}><Icon name="Table" /></span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>interview-themes.csv</div>
                <div className="sys-label" style={{ fontSize: 10.5, marginTop: 2 }}>Table · 12 rows · /product/interviews</div>
              </div>
            </a>
          </StashSection>

          {/* Shared pages */}
          <StashSection title="Shared pages" count={1} sub="Pages added by external collaborators — live in this stash, not in your workspace.">
            <a className="linkrow" style={{ padding: '10px 12px' }}>
              <span style={{ color: 'var(--brand-600)' }}><Icon name="Page" /></span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>Acme&apos;s 2026 dev-tools roadmap</div>
                <div className="sys-label" style={{ fontSize: 10.5, marginTop: 2 }}>added by Lila (Acme) · 3 days ago</div>
              </div>
              <span className="tag tag-warning">shared</span>
            </a>
          </StashSection>
        </div>
      </div>
    </AppShell>
  );
}

function StashSection({ title, count, sub, children }) {
  return (
    <section style={{ marginTop: 32 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, paddingBottom: 8, borderBottom: '1px solid var(--border-color)' }}>
        <h2 style={{
          fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700,
          letterSpacing: '-0.01em', margin: 0,
        }}>{title}</h2>
        <span className="sys-label">{count} items</span>
        <span style={{ flex: 1 }} />
        <button className="btn-ghost btn btn-sm">+ Add</button>
      </div>
      {sub && (
        <p style={{ marginTop: 10, fontSize: 12.5, color: 'var(--text-muted)' }}>{sub}</p>
      )}
      <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
        {children}
      </div>
    </section>
  );
}

function StashItemRow({ it }) {
  const iconColor = it.kind === 'html' ? '#D97706' : it.kind === 'table' ? '#16A34A' : 'var(--text-muted)';
  return (
    <a className="linkrow" style={{ padding: '10px 12px' }}>
      <span style={{ color: iconColor }}><Icon name={it.icon} /></span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.name}</div>
        <div className="sys-label" style={{ fontSize: 10.5, marginTop: 2 }}>{it.sub}</div>
      </div>
    </a>
  );
}

window.StashDetailScreen = StashDetailScreen;
