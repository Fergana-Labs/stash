// Screen: Session viewer
// Mirrors frontend/src/app/workspaces/[workspaceId]/sessions/[sessionId]/page.tsx
// Chat-style transcript with date dividers + right aside

const SESSION_TURNS = [
  { who: 'human', name: 'henry', time: '14:22', date: 'Today · May 17, 2026',
    content: "We need to wire the MCP server into our CLI surface so agents can call list-stashes, create-page, add-to-stash. Start with a plan in /cli/mcp/PLAN.md before touching any code." },
  { who: 'agent', name: 'agent', time: '14:22', agent: 'Codex · GPT-5.5 ultra',
    content: "Reading the existing CLI surface and our stash MCP draft. I'll scope this to the three commands you mentioned and identify auth touchpoints first." },
  { who: 'agent', name: 'agent', time: '14:23', toolName: 'read_file',
    content: "→ /cli/mcp/server.py (228 lines)\n→ /sdk/python/stash/__init__.py (412 lines)\n→ /backend/api/v1/stashes.py (180 lines)" },
  { who: 'agent', name: 'agent', time: '14:24', toolName: 'write_file',
    content: "→ /cli/mcp/PLAN.md\nDrafted plan: (1) add three tool definitions to the MCP server, (2) reuse workspace token from .stash, (3) write integration tests against the mock workspace fixture." },
  { who: 'agent', name: 'agent', time: '14:24',
    content: "Plan is in /cli/mcp/PLAN.md. Quick highlights:\n\n• list-stashes returns the workspace-visible stashes, paginated. We reuse list_stashes(workspaceId)\n• create-page accepts (folderId, name, content, content_type) — defaults markdown\n• add-to-stash takes (stashId, [{object_type, object_id, position?}]). Position auto-appends when omitted.\n\nProceed?" },
  { who: 'human', name: 'henry', time: '14:31',
    content: "Yes, proceed. Also: make sure shared-pages flow works. If the stash is external and the caller doesn't have a workspace seat, we create a shared_page instead of a normal page." },
  { who: 'agent', name: 'agent', time: '14:31', toolName: 'edit_file',
    content: "→ /cli/mcp/server.py — added three @tool decorators with input schemas. Routed create-page to /shared_pages when stash.workspace_id mismatches the caller's workspace." },
  { who: 'agent', name: 'agent', time: '14:32', toolName: 'run_tests',
    content: "$ pytest tests/cli/mcp -q\n........\n8 passed in 0.43s" },
  { who: 'agent', name: 'agent', time: '14:33',
    content: "All three commands wired and tested. Want me to add the same surface to the TypeScript SDK?" },
];

function MessageRow({ turn, isAgent }) {
  const avClass = isAgent ? 'av-violet' : turn.name === 'henry' ? 'av-indigo' : 'av-rose';
  return (
    <div style={{ display: 'flex', gap: 12, padding: '8px 8px' }}>
      <span className={'avatar ' + avClass} style={{ width: 28, height: 28, fontSize: 11 }}>
        {turn.name.slice(0,2).toUpperCase()}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>{turn.name}</span>
          {isAgent && <span className="tag tag-agent">agent</span>}
          {!isAgent && <span className="tag tag-human">human</span>}
          {turn.toolName && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 10.5,
              background: '#EEF2FF', color: '#3730A3',
              padding: '1px 6px', borderRadius: 3,
            }}>{turn.toolName}</span>
          )}
          {turn.agent && <span className="sys-label" style={{ fontSize: 10 }}>{turn.agent}</span>}
          <span style={{ flex: 1 }} />
          <span className="sys-label" style={{ fontSize: 10 }}>{turn.time}</span>
        </div>
        <div style={{
          marginTop: 4,
          whiteSpace: 'pre-wrap', fontSize: 13.5, lineHeight: 1.6,
          color: 'var(--text-primary)',
          fontFamily: turn.toolName ? 'var(--font-mono)' : 'var(--font-sans)',
          background: turn.toolName ? 'var(--bg-surface)' : 'transparent',
          padding: turn.toolName ? '8px 10px' : '0',
          borderRadius: turn.toolName ? 6 : 0,
          border: turn.toolName ? '1px solid var(--border-subtle-color)' : 'none',
          fontSize: turn.toolName ? 12 : 13.5,
        }}>
          {turn.content}
        </div>
      </div>
    </div>
  );
}

function SessionScreen() {
  return (
    <AppShell
      breadcrumb={['Sessions', '#henry-codex-3148']}
      activeSection=""
      activePage="henry-codex-3148"
    >
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 48px 80px',
        display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 260px', gap: 28 }}>

        {/* Main column */}
        <div style={{ minWidth: 0 }}>
          {/* Header */}
          <div style={{
            display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16,
            borderBottom: '1px solid var(--border-color)', paddingBottom: 14, marginBottom: 8,
          }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="tag tag-agent">agent · codex</span>
                <span className="sys-label">session</span>
              </div>
              <h1 style={{
                fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700,
                letterSpacing: '-0.02em', margin: '6px 0 0',
              }}>Wire up Stash MCP cli surface</h1>
              <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-muted)', display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                <span>Today · May 17, 2026</span>
                <span>·</span>
                <span>9 messages</span>
                <span>·</span>
                <span>kicked off by <span className="avatar av-indigo" style={{ width: 14, height: 14, fontSize: 8, marginRight: 4 }}>HP</span> Henry Patel</span>
                <span>·</span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>codex · gpt-5.5 ultra · thinking-high</span>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
              <button className="btn btn-sm"><Icon name="Download" /> JSONL</button>
              <button className="btn btn-sm"><Icon name="Plus" /> Add to stash</button>
            </div>
          </div>

          {/* Transcript */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '12px 0 4px', fontSize: 11, color: 'var(--text-muted)' }}>
              <span style={{ flex: 1, height: 1, background: 'var(--border-color)' }} />
              <span style={{ fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Today · May 17, 2026</span>
              <span style={{ flex: 1, height: 1, background: 'var(--border-color)' }} />
            </div>
            {SESSION_TURNS.map((t, i) => (
              <MessageRow key={i} turn={t} isAgent={t.who === 'agent'} />
            ))}

            {/* Composer */}
            <div style={{
              marginTop: 12, padding: 10,
              border: '1px solid var(--border-color)', borderRadius: 8,
              background: 'var(--bg-base)',
            }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <span className={'avatar ' + MOCK.user.avClass} style={{ width: 24, height: 24, fontSize: 10 }}>
                  {MOCK.user.initials}
                </span>
                <div style={{
                  flex: 1, minHeight: 40, padding: '6px 4px', fontSize: 13, color: 'var(--text-muted)',
                }}>
                  Reply or kick off a new agent turn…
                </div>
                <button className="btn btn-sm btn-primary"><Icon name="Send" /> Send</button>
              </div>
              <div style={{
                marginTop: 6, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                fontSize: 11, color: 'var(--text-muted)',
              }}>
                <span style={{ fontFamily: 'var(--font-mono)' }}>↳ continues this session in Codex · GPT-5.5 ultra</span>
                <div style={{ display: 'flex', gap: 6 }}>
                  <span className="tag tag-muted">/plan</span>
                  <span className="tag tag-muted">/files</span>
                  <span className="tag tag-muted">/stash</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Aside */}
        <aside style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="card-soft" style={{ padding: 14 }}>
            <div className="sys-label" style={{ fontSize: 11 }}>Artifacts</div>
            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {['cli/mcp/PLAN.md', 'cli/mcp/server.py', 'tests/cli/mcp/test_stash_tools.py', 'sdk/typescript/mcp/index.ts'].map((f, i) => (
                <div key={i} style={{
                  border: '1px solid var(--border-subtle-color)', background: 'var(--bg-base)',
                  borderRadius: 6, padding: '6px 8px', fontFamily: 'var(--font-mono)', fontSize: 11,
                  display: 'flex', alignItems: 'center', gap: 6,
                }}>
                  <Icon name="File" /><span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card-soft" style={{ padding: 14 }}>
            <div className="sys-label" style={{ fontSize: 11 }}>Tool calls</div>
            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {[
                ['read_file', '14:23 · 3 files'],
                ['write_file', '14:24 · PLAN.md'],
                ['edit_file', '14:31 · server.py'],
                ['run_tests', '14:32 · 8 passed'],
              ].map(([t, sub], i) => (
                <a key={i} className="linkrow" style={{ padding: '6px 8px' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-primary)' }}>{t}</span>
                  <span style={{ flex: 1 }} />
                  <span className="sys-label" style={{ fontSize: 10 }}>{sub}</span>
                </a>
              ))}
            </div>
          </div>

          <div className="card-soft" style={{ padding: 14 }}>
            <div className="sys-label" style={{ fontSize: 11 }}>In stashes</div>
            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {[['v0 launch prep', 14, 'workspace'], ['CLI / MCP work', 7, 'private']].map(([t, n, vis], i) => (
                <a key={i} className="linkrow" style={{ padding: '6px 8px' }}>
                  <span style={{ color: vis === 'private' ? '#9CA3AF' : 'var(--brand-600)' }}>
                    <Icon name="Stash" />
                  </span>
                  <span style={{ fontSize: 12.5, fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t}</span>
                  <span className="sys-label" style={{ fontSize: 10 }}>{n}</span>
                </a>
              ))}
              <button className="btn btn-sm" style={{ marginTop: 4 }}>
                <Icon name="Plus" /> Add to stash
              </button>
            </div>
          </div>

          <div className="card-soft" style={{ padding: 14 }}>
            <div className="sys-label" style={{ fontSize: 11 }}>Session metadata</div>
            <div style={{ marginTop: 8, fontSize: 11.5, color: 'var(--text-dim)', lineHeight: 1.7, fontFamily: 'var(--font-mono)' }}>
              <div>repo · /backend</div>
              <div>branch · feat/mcp-cli</div>
              <div>commit · 8f3a21d</div>
              <div>duration · 11m 04s</div>
              <div>turns · 31</div>
              <div>cost · $0.42</div>
            </div>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}

window.SessionScreen = SessionScreen;
