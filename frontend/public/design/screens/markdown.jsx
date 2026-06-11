// Screen: Markdown page viewer/editor — /workspaces/[ws]/p/[pageId] with content_type=markdown
// Uses brand-banner + page chrome + Notion-feel editable body.

function MarkdownScreen() {
  return (
    <AppShell
      breadcrumb={['product', 'PRD — Stash v0']}
      activeSection=""
      activePage="PRD — Stash v0"
    >
      <div className="scroll-thin" style={{ overflow: 'auto' }}>
        <div className="brand-banner" />
        <div style={{
          maxWidth: 1100, margin: '0 auto', padding: '0 48px 80px',
          display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 240px', gap: 32, marginTop: -22,
        }}>
          {/* Main */}
          <article style={{ minWidth: 0 }}>
            <span style={{
              width: 56, height: 56, borderRadius: 12,
              background: '#fff', border: '1px solid var(--border-color)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--text-muted)',
            }}>
              <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>
                <path d="M14 3v5h5"/>
                <path d="M9 13h6M9 17h4"/>
              </svg>
            </span>

            <h1 contentEditable={false} style={{
              fontFamily: 'var(--font-display)', fontSize: 38, fontWeight: 700,
              letterSpacing: '-0.025em', margin: '12px 0 4px',
            }}>PRD — Stash v0</h1>

            <div style={{
              display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: 'var(--text-muted)',
            }}>
              <span>Last edited May 17 · 10:31 by Aiyana</span>
              <span>·</span>
              <span style={{ color: 'var(--success)' }}>Saved</span>
              <span>·</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <span className="avatar av-rose" style={{ width: 16, height: 16, fontSize: 8 }}>AC</span>
                <span className="avatar av-indigo" style={{ width: 16, height: 16, fontSize: 8, marginLeft: -6 }}>HP</span>
                <span style={{ marginLeft: 4 }}>2 viewing</span>
              </span>
              <span style={{ flex: 1 }} />
              <button className="btn-ghost btn btn-sm"><Icon name="More" /></button>
            </div>

            {/* Edit toolbar (floating) */}
            <div style={{
              marginTop: 14,
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 6px', borderRadius: 8,
              border: '1px solid var(--border-color)', background: 'var(--bg-base)',
              boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
              width: 'fit-content',
            }}>
              {['B', 'I', 'U', 'S'].map((c, i) => (
                <span key={i} style={{
                  width: 24, height: 24, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: c === 'B' ? 700 : 500,
                  fontStyle: c === 'I' ? 'italic' : 'normal',
                  textDecoration: c === 'U' ? 'underline' : c === 'S' ? 'line-through' : 'none',
                  color: 'var(--text-dim)', cursor: 'pointer', borderRadius: 4,
                }}>{c}</span>
              ))}
              <span style={{ width: 1, height: 16, background: 'var(--border-color)', margin: '0 4px' }} />
              <span style={{ padding: '0 6px', fontSize: 11.5, color: 'var(--text-dim)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}>
                H2 <Icon name="ChevDown" />
              </span>
              <span style={{ width: 1, height: 16, background: 'var(--border-color)', margin: '0 4px' }} />
              <span style={{ padding: '0 6px', fontSize: 12, color: 'var(--text-dim)', cursor: 'pointer' }}>
                <Icon name="Code" />
              </span>
              <span style={{ padding: '0 6px', fontSize: 12, color: 'var(--text-dim)', cursor: 'pointer' }}>
                <Icon name="Sparkle" />
              </span>
              <span style={{ width: 1, height: 16, background: 'var(--border-color)', margin: '0 4px' }} />
              <span style={{ padding: '2px 8px', fontSize: 11.5, color: 'var(--brand-700)', background: 'var(--brand-50)', borderRadius: 4, cursor: 'pointer' }}>
                Ask the workspace
              </span>
            </div>

            <div className="proseish" style={{ marginTop: 20 }}>
              <p style={{ fontSize: 16.5, color: 'var(--text-primary)', lineHeight: 1.6 }}>
                Stash is the place agents and humans dump work, and stashes are how we make sense of it. This doc captures the v0 product surface.
              </p>

              <h2>Three primitives</h2>
              <p>The whole product is just three things, and we keep them llm-legible:</p>
              <ul>
                <li><strong>Sessions</strong> — every agent transcript and its artifacts (e.g. a temporary <code>PLAN.md</code>).</li>
                <li><strong>Drive</strong> — a real filesystem of pages, folders, and tables. No subpages, no blocks, no wiki-isms.</li>
                <li><strong>Stashes</strong> — our novel unit. A user-curated bundle of sessions and pages with a single permission level (<code>workspace</code> / <code>private</code> / <code>public</code>). Stashes are how privacy works. They are also how things get shared.</li>
              </ul>

              <h2>Cartridges, not folders</h2>
              <blockquote>
                We&apos;re betting that a stash is the right unit to share — better than a folder, better than a doc.
                You hand someone a stash the way a character in <em>The Matrix</em> hands you a cartridge.
              </blockquote>

              <h2>Open questions</h2>
              <p>Track these in <a>Open questions</a> — moving the resolved ones below.</p>
              <ul>
                <li>What&apos;s on the user&apos;s homepage? <strong>Newsfeed</strong>.</li>
                <li>Discover in scope for v0? <strong>Yes</strong>.</li>
                <li>Tables = page or separate type? <strong>Separate type</strong>.</li>
                <li>Folders? <strong>Yes</strong>. Subpages? <strong>No</strong>.</li>
              </ul>

              <h2>Out of scope</h2>
              <p>
                Anything we&apos;d call a &quot;curator agent.&quot; Sleep-time compute over the filesystem. Version history.
                Integrations of any kind for v0 (slack, granola, drive). All fast follows.
              </p>

              {/* Phantom cursor */}
              <p style={{ color: 'var(--text-muted)', fontStyle: 'italic', display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  display: 'inline-block', width: 2, height: 18, background: '#1D4ED8',
                  position: 'relative', verticalAlign: 'middle',
                }}>
                  <span style={{
                    position: 'absolute', top: -16, left: -1, padding: '1px 5px',
                    background: '#1D4ED8', color: '#fff', fontSize: 10, borderRadius: '3px 3px 3px 0',
                    fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap',
                  }}>henry</span>
                </span>
                <span>Henry is typing a section on shared-pages…</span>
              </p>
            </div>

            {/* slash-menu hint */}
            <div style={{
              marginTop: 24, padding: '10px 12px', borderRadius: 8,
              background: 'var(--bg-surface)', border: '1px dashed var(--border-color)',
              fontSize: 12.5, color: 'var(--text-muted)',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>/</span>
              press <span style={{ fontFamily: 'var(--font-mono)', background: 'var(--bg-raised)', padding: '0 5px', borderRadius: 3 }}>/</span> for blocks ·
              <span style={{ fontFamily: 'var(--font-mono)', background: 'var(--bg-raised)', padding: '0 5px', borderRadius: 3 }}>@</span> for pages or people ·
              <span style={{ fontFamily: 'var(--font-mono)', background: 'var(--bg-raised)', padding: '0 5px', borderRadius: 3 }}>⌘+J</span> to ask the workspace
            </div>
          </article>

          {/* Aside */}
          <aside style={{ marginTop: 80, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="card-soft" style={{ padding: 14 }}>
              <div className="sys-label">On this page</div>
              <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12.5 }}>
                {[
                  ['Three primitives', 0],
                  ['Cartridges, not folders', 0],
                  ['Open questions', 0],
                  ['Out of scope', 0],
                ].map(([t, indent], i) => (
                  <a key={i} style={{
                    paddingLeft: 6 + (indent * 10), color: 'var(--text-dim)',
                    cursor: 'pointer', padding: '2px 6px', borderRadius: 4,
                    background: i === 0 ? 'var(--bg-raised)' : 'transparent',
                  }}>{t}</a>
                ))}
              </div>
            </div>

            <div className="card-soft" style={{ padding: 14 }}>
              <div className="sys-label">In stashes</div>
              <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {[['v0 launch prep', 14, false], ['Customer interviews · oct', 22, false]].map(([t, n], i) => (
                  <a key={i} className="linkrow" style={{ padding: '6px 8px' }}>
                    <span style={{ color: 'var(--brand-600)' }}><Icon name="Stash" /></span>
                    <span style={{ fontSize: 12.5, fontWeight: 500, flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t}</span>
                    <span className="sys-label" style={{ fontSize: 10 }}>{n}</span>
                  </a>
                ))}
              </div>
            </div>

            <div className="card-soft" style={{ padding: 14 }}>
              <div className="sys-label">Recent edits</div>
              <div style={{ marginTop: 8, fontSize: 11.5, color: 'var(--text-dim)', lineHeight: 1.6 }}>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
                  <span className="avatar av-rose" style={{ width: 16, height: 16, fontSize: 8 }}>AC</span>
                  <span><strong style={{ color: 'var(--text-primary)' }}>Aiyana</strong> resolved 4 open questions</span>
                </div>
                <div style={{ marginLeft: 22, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 10.5 }}>38m ago</div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 10, marginBottom: 6 }}>
                  <span className="avatar av-violet" style={{ width: 16, height: 16, fontSize: 8 }}>AG</span>
                  <span><strong style={{ color: 'var(--text-primary)' }}>agent</strong> rewrote the intro paragraph</span>
                </div>
                <div style={{ marginLeft: 22, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 10.5 }}>2h ago · session #aiyana-claude-3146</div>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}

window.MarkdownScreen = MarkdownScreen;
