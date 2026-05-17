// AppShell — top bar + sidebar that wraps every screen
const { useState } = React;

function TopBar({ breadcrumb, workspaceName }) {
  const wsName = workspaceName || MOCK.workspace.name;
  return (
    <header
      style={{
        height: 44,
        flexShrink: 0,
        display: 'grid',
        gridTemplateColumns: 'minmax(0,1fr) minmax(260px, 480px) minmax(0,1fr)',
        alignItems: 'center',
        gap: 12,
        borderBottom: '1px solid var(--border-color)',
        padding: '0 12px',
        background: 'rgba(255,255,255,0.88)',
        backdropFilter: 'blur(8px)',
      }}
    >
      {/* Left — workspace + breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, minWidth: 0, fontSize: 13 }}>
        <button className="btn-ghost btn btn-sm" style={{ padding: 4 }} aria-label="Toggle sidebar">
          <Icon name="Sidebar" />
        </button>
        <button className="btn-ghost btn btn-sm" style={{ padding: 4 }} aria-label="Back">
          <Icon name="Back" />
        </button>

        <a style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '4px 6px', borderRadius: 4, color: 'var(--text-primary)',
          marginLeft: 4,
        }}>
          <StashLogo size={16} />
          <span style={{ fontWeight: 500, fontSize: 13 }}>{wsName}</span>
        </a>

        <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)', minWidth: 0 }}>
          {breadcrumb && breadcrumb.map((c, i) => (
            <React.Fragment key={i}>
              <span style={{ color: 'rgba(155,154,151,0.6)' }}>/</span>
              <span
                style={{
                  whiteSpace: 'nowrap',
                  overflow: 'hidden', textOverflow: 'ellipsis',
                  maxWidth: 160,
                  fontWeight: i === breadcrumb.length - 1 ? 500 : 400,
                  color: i === breadcrumb.length - 1 ? 'var(--text-primary)' : 'var(--text-muted)',
                }}
              >
                {c}
              </span>
            </React.Fragment>
          ))}
        </span>
      </div>

      {/* Center — search */}
      <button
        style={{
          height: 28,
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '0 10px',
          borderRadius: 6,
          border: '1px solid var(--border-color)',
          background: 'var(--bg-surface)',
          color: 'var(--text-muted)',
          fontSize: 12.5, textAlign: 'left',
          width: '100%',
          cursor: 'pointer',
        }}
      >
        <Icon name="Search" />
        <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          Search {wsName}
        </span>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 10,
          background: 'var(--bg-base)', border: '1px solid var(--border-color)',
          padding: '1px 5px', borderRadius: 3,
        }}>⌘K</span>
      </button>

      {/* Right — share + user */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
        <button className="btn btn-sm btn-ghost" style={{ padding: 4 }} aria-label="Activity">
          <Icon name="Bell" />
        </button>
        <button className="btn-primary btn btn-sm">Share</button>
        <span
          className={'avatar ' + MOCK.user.avClass}
          style={{ width: 24, height: 24, marginLeft: 4 }}
        >
          {MOCK.user.initials}
        </span>
      </div>
    </header>
  );
}

function TreeNode({ node, depth = 0, activeId }) {
  const [open, setOpen] = useState(!!node.open);
  if (node.type === 'folder') {
    return (
      <div>
        <div className="side-row" onClick={() => setOpen(!open)}
          style={{ paddingLeft: 8 + depth * 12 }}>
          <span
            style={{
              transform: open ? 'rotate(90deg)' : 'none',
              transition: 'transform .12s ease',
              display: 'inline-flex',
              color: 'var(--text-muted)',
            }}
          >
            <Icon name="Chev" />
          </span>
          <span style={{ color: 'var(--text-muted)' }}><Icon name={open ? 'FolderOpen' : 'Folder'} /></span>
          <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {node.name}
          </span>
        </div>
        {open && node.children && (
          <div>
            {node.children.map((c, i) => <TreeNode key={i} node={c} depth={depth + 1} activeId={activeId} />)}
          </div>
        )}
      </div>
    );
  }

  const iconName = node.type === 'table' ? 'Table' : node.type === 'html' ? 'Html' : 'Page';
  const isActive = activeId && node.name === activeId;
  return (
    <div
      className={'side-row' + (isActive ? ' active' : '')}
      style={{ paddingLeft: 8 + depth * 12 + 14 }}
    >
      <span style={{ color: 'var(--text-muted)' }}><Icon name={iconName} /></span>
      <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {node.name}
      </span>
    </div>
  );
}

function Sidebar({ activeSection, activePage }) {
  return (
    <aside
      className="scroll-thin"
      style={{
        width: 260,
        borderRight: '1px solid var(--border-color)',
        background: 'var(--bg-surface)',
        overflow: 'auto',
        padding: '6px 6px',
        display: 'flex', flexDirection: 'column', gap: 4,
        height: '100%',
      }}
    >
      {/* Workspace switcher */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 8px', borderRadius: 6,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <StashLogo size={20} />
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>Fergana Labs</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>6 members</span>
          </div>
        </div>
        <Icon name="ChevDown" />
      </div>

      {/* Quick actions */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1, padding: '2px 0' }}>
        <div className={'side-row' + (activeSection === 'home' ? ' active' : '')}>
          <span style={{ color: 'var(--text-muted)' }}><Icon name="Activity" /></span>
          <span style={{ flex: 1 }}>Home</span>
        </div>
        <div className={'side-row' + (activeSection === 'discover' ? ' active' : '')}>
          <span style={{ color: 'var(--text-muted)' }}><Icon name="Globe" /></span>
          <span style={{ flex: 1 }}>Discover</span>
          <span className="sys-label" style={{ color: 'var(--brand-700)' }}>2</span>
        </div>
        <div className={'side-row' + (activeSection === 'activity' ? ' active' : '')}>
          <span style={{ color: 'var(--text-muted)' }}><Icon name="Eye" /></span>
          <span style={{ flex: 1 }}>Activity</span>
        </div>
      </div>

      {/* Pinned stashes */}
      <div>
        <div className="side-section-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Stashes</span>
          <button className="btn-ghost" style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <Icon name="Plus" />
          </button>
        </div>
        {MOCK.pinnedStashes.map((s, i) => (
          <div key={i} className={'side-row' + (activePage === s.name ? ' active' : '')}>
            <span style={{ color: s.visibility === 'public' ? '#22C55E' : s.visibility === 'private' ? '#9CA3AF' : 'var(--brand-500)' }}>
              <Icon name="Stash" />
            </span>
            <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {s.name}
            </span>
            <span className="sys-label" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{s.items}</span>
          </div>
        ))}
      </div>

      {/* Filesystem */}
      <div>
        <div className="side-section-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Files</span>
          <button className="btn-ghost" style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <Icon name="Plus" />
          </button>
        </div>
        {MOCK.tree.map((n, i) => <TreeNode key={i} node={n} activeId={activePage} />)}
      </div>

      {/* Sessions */}
      <div>
        <div className="side-section-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Sessions</span>
          <span className="sys-label" style={{ fontSize: 10 }}>{
            MOCK.sessionDays.reduce((acc, d) => acc + d.users.reduce((a, u) => a + u.sessions.length, 0), 0)
          }</span>
        </div>
        {MOCK.sessionDays.map((day, i) => (
          <div key={i} style={{ marginTop: i === 0 ? 0 : 6 }}>
            <div style={{ padding: '4px 8px', fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              {day.label}
            </div>
            {day.users.map((u, j) => (
              <div key={j} style={{ marginBottom: 2 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 8px' }}>
                  <span className={'avatar ' + u.avClass} style={{ width: 16, height: 16, fontSize: 8.5 }}>
                    {u.user.slice(0,2).toUpperCase()}
                  </span>
                  <span style={{ fontSize: 11.5, color: 'var(--text-dim)', fontWeight: 500 }}>{u.user}</span>
                </div>
                {u.sessions.map((s, k) => (
                  <div
                    key={k}
                    className={'side-row' + (activePage === s.id ? ' active' : '')}
                    style={{ paddingLeft: 32 }}
                  >
                    <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 12.5 }}>
                      {s.title}
                    </span>
                    <span className="sys-label" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{s.time}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>

      <div style={{ flex: 1 }} />
    </aside>
  );
}

function AppShell({ breadcrumb, activeSection, activePage, workspaceName, children, hideSidebar }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-base)' }}>
      <TopBar breadcrumb={breadcrumb} workspaceName={workspaceName} />
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {!hideSidebar && <Sidebar activeSection={activeSection} activePage={activePage} />}
        <main className="scroll-thin" style={{ flex: 1, minWidth: 0, overflow: 'auto', background: 'var(--bg-base)' }}>
          {children}
        </main>
      </div>
    </div>
  );
}

window.AppShell = AppShell;
window.TopBar = TopBar;
window.Sidebar = Sidebar;
