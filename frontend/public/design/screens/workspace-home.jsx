// Screens: Workspace Home (newsfeed), Activity-style updates
// Layout uses standard page chrome (no banner — this is the home/feed)

function FeedItemIcon({ kind }) {
  if (kind === 'session-pinned' || kind === 'session-added') {
    return <span style={{ color: 'var(--agent)' }}><Icon name="Session" /></span>;
  }
  if (kind === 'page-edited') {
    return <span style={{ color: 'var(--text-muted)' }}><Icon name="Page" /></span>;
  }
  if (kind === 'stash-published') {
    return <span style={{ color: 'var(--brand-600)' }}><Icon name="Stash" /></span>;
  }
  if (kind === 'discover') {
    return <span style={{ color: 'var(--text-muted)' }}><Icon name="Globe" /></span>;
  }
  return null;
}

function StashChips({ list, max = 3 }) {
  if (!list || !list.length) return null;
  const shown = list.slice(0, max);
  const overflow = list.length - shown.length;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      {shown.map((s, i) => (
        <span key={i} className="stash-chip">
          <span className="dot" />{s}
        </span>
      ))}
      {overflow > 0 && <span className="sys-label" style={{ fontSize: 10 }}>+{overflow}</span>}
    </div>
  );
}

function FeedItem({ item }) {
  const isDiscover = item.kind === 'discover';
  return (
    <article
      className="card"
      style={{ padding: '14px 16px', display: 'flex', gap: 12, alignItems: 'flex-start' }}
    >
      <div style={{ marginTop: 1 }}>
        {item.user ? (
          <span className={'avatar ' + item.avClass} style={{ width: 28, height: 28, fontSize: 11 }}>
            {item.user.slice(0,2).toUpperCase()}
          </span>
        ) : (
          <span className="avatar av-violet" style={{ width: 28, height: 28 }}>
            <Icon name="Globe" />
          </span>
        )}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>
            {item.user ? <strong style={{ color: 'var(--text-primary)' }}>{item.user}</strong> : <span>From <strong style={{ color: 'var(--text-primary)' }}>Discover</strong></span>}
            {item.kind === 'session-pinned' && ' pinned a session'}
            {item.kind === 'session-added' && ' streamed a new session'}
            {item.kind === 'page-edited' && ' edited a page'}
            {item.kind === 'stash-published' && ' published a stash'}
            {item.kind === 'discover' && ' — a new external stash you might like'}
          </span>
          <span className="sys-label" style={{ fontSize: 10.5 }}>{item.time}</span>
          {item.kind === 'session-pinned' && <span className="tag tag-agent">agent</span>}
          {item.kind === 'session-added' && <span className="tag tag-agent">agent</span>}
          {item.kind === 'page-edited' && <span className="tag tag-human">human</span>}
        </div>

        <h3 style={{
          fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 700,
          margin: '6px 0 4px', letterSpacing: '-0.01em',
        }}>
          <span style={{ color: 'var(--text-muted)', marginRight: 6, verticalAlign: 'middle', display: 'inline-flex' }}>
            <FeedItemIcon kind={item.kind} />
          </span>
          {item.title}
        </h3>

        <p style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--text-dim)', margin: '4px 0 10px' }}>
          {item.summary}
        </p>

        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
          fontSize: 11.5, color: 'var(--text-muted)',
        }}>
          {item.meta?.agent && (
            <span style={{ fontFamily: 'var(--font-mono)' }}>{item.meta.agent}</span>
          )}
          {item.meta?.turns && <span>· {item.meta.turns} turns</span>}
          {item.meta?.files && <span>· {item.meta.files} files</span>}
          {item.meta?.folder && <span>· in <span style={{ color: 'var(--text-dim)' }}>{item.meta.folder}</span></span>}
          {item.meta?.visibility && (
            <span className={'stash-chip ' + item.meta.visibility} style={{ padding: '1px 7px' }}>
              <span className="dot" />{item.meta.visibility}
            </span>
          )}
          {item.meta?.items && <span>· {item.meta.items} items</span>}
          {item.meta?.views && <span>· {item.meta.views} views</span>}
          {item.meta?.source && <span>· {item.meta.source}</span>}

          {item.stashes && (
            <>
              <span style={{ width: 1, height: 12, background: 'var(--border-color)', margin: '0 2px' }} />
              <StashChips list={item.stashes} />
            </>
          )}

          <span style={{ flex: 1 }} />
          {isDiscover ? (
            <button className="btn btn-sm">
              <Icon name="Plus" /> Add to workspace
            </button>
          ) : (
            <button className="btn-ghost btn btn-sm">Open <Icon name="ArrowRight" /></button>
          )}
        </div>
      </div>
    </article>
  );
}

function WorkspaceHomeScreen() {
  return (
    <AppShell breadcrumb={['Home']} activeSection="home" activePage="">
      <div style={{ maxWidth: 920, margin: '0 auto', padding: '36px 48px 80px' }}>
        {/* Hero */}
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 24 }}>
          <div>
            <div className="sys-label">Workspace · 6 members · 4 GitHub repos</div>
            <h1 style={{
              fontFamily: 'var(--font-display)', fontSize: 40, fontWeight: 900,
              letterSpacing: '-0.025em', margin: '6px 0 4px', lineHeight: 1.05,
            }}>
              Hi Aiyana — <span style={{ color: 'var(--text-muted)' }}>here&apos;s what your agents shipped.</span>
            </h1>
            <p style={{ fontSize: 14.5, color: 'var(--text-dim)', margin: '4px 0 0', maxWidth: 620 }}>
              31 sessions, 14 pages and 2 new stashes since you last checked in three hours ago.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
            <button className="btn btn-sm"><Icon name="Plus" /> New stash</button>
            <button className="btn btn-sm"><Icon name="Plus" /> New page</button>
          </div>
        </div>

        {/* Stat strip */}
        <div style={{
          marginTop: 24,
          display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10,
        }}>
          {[
            { label: 'Sessions today', value: '12', tint: 'var(--agent)' },
            { label: 'Pages edited', value: '8', tint: 'var(--human)' },
            { label: 'Active stashes', value: '14', tint: 'var(--brand-500)' },
            { label: 'External stashes', value: '5', tint: 'var(--text-muted)' },
          ].map((s, i) => (
            <div key={i} className="card" style={{ padding: '12px 14px' }}>
              <div style={{
                fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 700,
                letterSpacing: '-0.02em', color: s.tint, lineHeight: 1.1,
              }}>{s.value}</div>
              <div className="sys-label" style={{ marginTop: 2 }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div style={{
          marginTop: 32,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          paddingBottom: 8, borderBottom: '1px solid var(--border-color)',
        }}>
          <div style={{ display: 'flex', gap: 4 }}>
            {['Everything', 'Sessions', 'Pages', 'Stashes', 'From discover'].map((label, i) => (
              <button
                key={i}
                className={i === 0 ? '' : 'btn-ghost'}
                style={{
                  background: i === 0 ? 'var(--bg-raised)' : 'transparent',
                  border: 'none', padding: '4px 10px',
                  fontSize: 12.5, fontWeight: i === 0 ? 600 : 400,
                  borderRadius: 6, cursor: 'pointer',
                  color: i === 0 ? 'var(--text-primary)' : 'var(--text-muted)',
                }}
              >{label}</button>
            ))}
          </div>
          <span className="sys-label">sorted · recent</span>
        </div>

        {/* Feed */}
        <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {MOCK.feed.map((item, i) => <FeedItem key={i} item={item} />)}
        </div>
      </div>
    </AppShell>
  );
}

window.WorkspaceHomeScreen = WorkspaceHomeScreen;
