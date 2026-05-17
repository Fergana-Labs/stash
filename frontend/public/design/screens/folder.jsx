// Screen: Folder browser — /workspaces/[ws]/folders/[id]
// Breadcrumb + folder icon + grid of items

const FOLDER_ITEMS = [
  { kind: 'folder', name: 'interviews', sub: '8 pages · 1 table', icon: 'FolderOpen' },
  { kind: 'folder', name: 'discovery research', sub: '12 pages', icon: 'Folder' },
  { kind: 'folder', name: 'old briefs', sub: '4 pages', icon: 'Folder' },
  { kind: 'page', name: 'PRD — Stash v0', sub: 'Page · markdown · edited 38m ago', icon: 'Page' },
  { kind: 'page', name: 'Open questions', sub: 'Page · markdown · edited 1d ago', icon: 'Page' },
  { kind: 'page', name: 'Naming brainstorm', sub: 'Page · markdown · edited 3d ago', icon: 'Page' },
  { kind: 'html', name: 'launch-narrative-v3.html', sub: 'Page · html · edited 4h ago', icon: 'Html' },
  { kind: 'table', name: 'interview-themes.csv', sub: 'Table · 12 rows · synced 4m ago', icon: 'Table' },
  { kind: 'file', name: 'persona-deck.pdf', sub: 'pdf · 1.4 MB', icon: 'File' },
  { kind: 'image', name: 'whiteboard-may-12.png', sub: 'image · 480 KB', icon: 'Image' },
];

function FolderTile({ item }) {
  const iconColor = item.kind === 'folder' ? 'var(--text-muted)'
    : item.kind === 'html' ? '#D97706'
    : item.kind === 'table' ? '#16A34A'
    : item.kind === 'image' ? '#7C3AED'
    : item.kind === 'file' ? '#DC2626'
    : 'var(--text-muted)';

  return (
    <a className="linkrow" style={{ padding: '12px 14px', alignItems: 'flex-start' }}>
      <span style={{ color: iconColor, marginTop: 2 }}>
        <Icon name={item.icon} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 13.5, fontWeight: 600, color: 'var(--text-primary)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>{item.name}</div>
        <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
          {item.sub}
        </div>
      </div>
      <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>
        <Icon name="More" />
      </span>
    </a>
  );
}

function FolderScreen() {
  const folders = FOLDER_ITEMS.filter(i => i.kind === 'folder');
  const pages = FOLDER_ITEMS.filter(i => i.kind === 'page' || i.kind === 'html');
  const tables = FOLDER_ITEMS.filter(i => i.kind === 'table');
  const files = FOLDER_ITEMS.filter(i => i.kind === 'file' || i.kind === 'image');

  return (
    <AppShell
      breadcrumb={['product']}
      activeSection=""
      activePage=""
    >
      <div style={{ maxWidth: 980, margin: '0 auto', padding: '32px 48px 80px' }}>
        {/* Breadcrumb path */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--text-muted)' }}>
          <span style={{ color: 'var(--text-dim)' }}>Home</span>
          <span style={{ color: 'rgba(155,154,151,0.6)' }}>/</span>
          <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>product</span>
        </div>

        {/* Header */}
        <div style={{ marginTop: 14, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <span style={{
              width: 44, height: 44, borderRadius: 10,
              background: 'var(--bg-surface)', border: '1px solid var(--border-color)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--text-dim)',
            }}>
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>
              </svg>
            </span>
            <h1 style={{
              fontFamily: 'var(--font-display)', fontSize: 30, fontWeight: 700,
              letterSpacing: '-0.02em', margin: '10px 0 4px',
            }}>product</h1>
            <div style={{ fontSize: 12.5, color: 'var(--text-muted)', display: 'flex', gap: 8, alignItems: 'center' }}>
              <span>3 folders · 6 pages · 1 table · 2 files</span>
              <span>·</span>
              <span className="stash-chip"><span className="dot" />v0 launch prep</span>
              <span className="stash-chip"><span className="dot" />Customer interviews · oct</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-sm"><Icon name="Plus" /> Upload file</button>
            <button className="btn btn-sm"><Icon name="Plus" /> New page</button>
            <button className="btn btn-sm"><Icon name="Plus" /> New folder</button>
          </div>
        </div>

        {/* Toolbar */}
        <div style={{
          marginTop: 22, display: 'flex', alignItems: 'center', gap: 6,
          paddingBottom: 8, borderBottom: '1px solid var(--border-color)',
        }}>
          <button className="btn btn-sm" style={{ background: 'var(--bg-raised)' }}>
            <span style={{ color: 'var(--text-muted)' }}>sort ·</span>
            <span style={{ fontWeight: 500 }}>edited</span>
            <Icon name="ChevDown" />
          </button>
          <button className="btn-ghost btn btn-sm">⊞ Grid</button>
          <button className="btn btn-sm" style={{ background: 'var(--bg-raised)' }}>≡ List</button>
          <span style={{ flex: 1 }} />
          <span className="sys-label" style={{ fontSize: 10.5 }}>showing 10 of 10</span>
        </div>

        {/* Folders */}
        <Section title="Folders" count={folders.length}>
          {folders.map((it, i) => <FolderTile key={i} item={it} />)}
        </Section>

        <Section title="Pages" count={pages.length}>
          {pages.map((it, i) => <FolderTile key={i} item={it} />)}
        </Section>

        <Section title="Tables" count={tables.length}>
          {tables.map((it, i) => <FolderTile key={i} item={it} />)}
        </Section>

        <Section title="Files" count={files.length}>
          {files.map((it, i) => <FolderTile key={i} item={it} />)}
        </Section>
      </div>
    </AppShell>
  );
}

function Section({ title, count, children }) {
  return (
    <section style={{ marginTop: 22 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
        <h2 style={{
          fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 600,
          letterSpacing: '-0.005em', margin: 0,
        }}>{title}</h2>
        <span className="sys-label" style={{ fontSize: 10.5 }}>{count}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
        {children}
      </div>
    </section>
  );
}

window.FolderScreen = FolderScreen;
