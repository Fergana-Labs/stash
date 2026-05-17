// Screen: Table viewer (csv-as-page) — /tables/[tableId]
// Spreadsheet-like view with column types and a side panel.

const TABLE_HEADERS = [
  { name: 'Theme', kind: 'text', width: 200 },
  { name: 'Severity', kind: 'select', width: 110 },
  { name: 'Mentions', kind: 'number', width: 100 },
  { name: 'Top interview', kind: 'page', width: 220 },
  { name: 'Owner', kind: 'person', width: 140 },
  { name: 'Open?', kind: 'check', width: 80 },
  { name: 'Last updated', kind: 'date', width: 130 },
];

const TABLE_ROWS = [
  ['Sessions ordering by user/day is critical', 'high', 12, 'Mara — Acme dev tools', { name: 'Aiyana', av: 'av-rose' }, true, 'May 16'],
  ['"Add to workspace" must be a fork, not ref', 'high', 9, 'Henry — Replicant infra', { name: 'Henry', av: 'av-indigo' }, true, 'May 15'],
  ['Stash discovery via shareable links', 'med', 8, 'Priya — Granola pm', { name: 'Dani', av: 'av-amber' }, false, 'May 14'],
  ['CSV files should open as tables', 'med', 7, 'Mara — Acme dev tools', { name: 'Mara', av: 'av-emerald' }, false, 'May 14'],
  ['Search must scope to current stash', 'med', 6, 'Priya — Granola pm', { name: 'Sam', av: 'av-sky' }, true, 'May 12'],
  ['Speak to "live vs snapshot" up-front', 'med', 5, 'Henry — Replicant infra', { name: 'Aiyana', av: 'av-rose' }, false, 'May 12'],
  ['Workspace ≠ tenant: it\'s about belonging', 'low', 4, 'Mara — Acme dev tools', { name: 'Priya', av: 'av-fuchsia' }, true, 'May 10'],
  ['Pasting MCP key in claude code should "just work"', 'high', 11, 'Henry — Replicant infra', { name: 'Henry', av: 'av-indigo' }, false, 'May 10'],
  ['Tables are weird inside pages — keep separate', 'low', 3, 'Priya — Granola pm', { name: 'Mara', av: 'av-emerald' }, false, 'May 09'],
  ['Default visibility should be workspace', 'low', 3, 'Mara — Acme dev tools', { name: 'Sam', av: 'av-sky' }, true, 'May 09'],
  ['Sidebar density: comfortable, not compact', 'low', 2, 'Henry — Replicant infra', { name: 'Aiyana', av: 'av-rose' }, true, 'May 08'],
  ['Agents need to see stash boundaries clearly', 'med', 4, 'Priya — Granola pm', { name: 'Dani', av: 'av-amber' }, false, 'May 08'],
];

function SeverityPill({ value }) {
  const map = {
    high: { bg: 'rgba(239,68,68,0.12)', fg: '#B91C1C' },
    med: { bg: 'rgba(234,179,8,0.18)', fg: '#854D0E' },
    low: { bg: 'var(--bg-raised)', fg: 'var(--text-dim)' },
  };
  const c = map[value];
  return (
    <span style={{
      display: 'inline-block',
      padding: '1px 8px',
      borderRadius: 999,
      fontSize: 10.5, fontWeight: 500, textTransform: 'uppercase',
      letterSpacing: '0.04em',
      background: c.bg, color: c.fg,
      fontFamily: 'var(--font-mono)',
    }}>{value}</span>
  );
}

function TableScreen() {
  return (
    <AppShell
      breadcrumb={['product', 'interviews', 'interview-themes.csv']}
      activeSection=""
      activePage="interview-themes.csv"
    >
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* Title strip */}
        <div style={{
          padding: '16px 28px 12px',
          borderBottom: '1px solid var(--border-color)',
          background: 'var(--bg-base)',
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ color: '#16A34A' }}><Icon name="Table" /></span>
                <span className="sys-label">csv · 12 rows · 7 cols</span>
                <span className="tag tag-success">linked</span>
              </div>
              <h1 style={{
                fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 700,
                letterSpacing: '-0.02em', margin: '4px 0 0',
              }}>interview-themes.csv</h1>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button className="btn btn-sm"><Icon name="Plus" /> Row</button>
              <button className="btn btn-sm"><Icon name="Plus" /> Column</button>
              <button className="btn btn-sm"><Icon name="Download" /> CSV</button>
              <button className="btn btn-sm btn-primary"><Icon name="Plus" /> Add to stash</button>
            </div>
          </div>

          {/* Filter row */}
          <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
            <button className="btn btn-sm" style={{ background: 'var(--bg-raised)' }}>
              <span style={{ color: 'var(--text-muted)' }}>view ·</span>
              <span style={{ fontWeight: 500 }}>all rows</span>
              <Icon name="ChevDown" />
            </button>
            <button className="btn btn-sm">+ Filter</button>
            <button className="btn btn-sm">+ Sort</button>
            <button className="btn btn-sm">Group</button>
            <span style={{ flex: 1 }} />
            <span className="sys-label" style={{ fontSize: 10.5 }}>linked from /product/interviews/interview-themes.csv · synced 4 min ago</span>
          </div>
        </div>

        {/* Table */}
        <div className="scroll-thin" style={{ flex: 1, overflow: 'auto', padding: '0 28px 24px' }}>
          <div style={{
            border: '1px solid var(--border-color)',
            borderRadius: 8, overflow: 'hidden',
            marginTop: 12, background: 'var(--bg-base)',
          }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th className="row-num">#</th>
                  {TABLE_HEADERS.map((h, i) => (
                    <th key={i} className={h.kind === 'number' ? 'num' : ''} style={{ width: h.width }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ color: 'var(--text-muted)' }}>
                          {h.kind === 'text' && 'Aa'}
                          {h.kind === 'select' && '◉'}
                          {h.kind === 'number' && '#'}
                          {h.kind === 'page' && '↳'}
                          {h.kind === 'person' && '@'}
                          {h.kind === 'check' && '☐'}
                          {h.kind === 'date' && '📅'}
                        </span>
                        {h.name}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {TABLE_ROWS.map((row, i) => (
                  <tr key={i}>
                    <td className="row-num">{i + 1}</td>
                    <td>
                      <span style={{ color: 'var(--text-primary)' }}>{row[0]}</span>
                    </td>
                    <td><SeverityPill value={row[1]} /></td>
                    <td className="num">{row[2]}</td>
                    <td>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: 6,
                        color: 'var(--brand-700)',
                        textDecoration: 'underline', textUnderlineOffset: 2,
                      }}>
                        <span style={{ color: 'var(--text-muted)' }}><Icon name="Page" /></span>
                        {row[3]}
                      </span>
                    </td>
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span className={'avatar ' + row[4].av} style={{ width: 18, height: 18, fontSize: 9 }}>
                          {row[4].name.slice(0,2).toUpperCase()}
                        </span>
                        {row[4].name}
                      </span>
                    </td>
                    <td>
                      <span style={{
                        display: 'inline-block', width: 14, height: 14, borderRadius: 3,
                        border: '1.5px solid ' + (row[5] ? 'var(--brand-500)' : 'var(--text-muted)'),
                        background: row[5] ? 'var(--brand-500)' : 'transparent',
                        position: 'relative', verticalAlign: 'middle',
                      }}>
                        {row[5] && (
                          <span style={{
                            position: 'absolute', inset: 0, color: '#fff', fontSize: 9.5, fontWeight: 700,
                            display: 'flex', alignItems: 'center', justifyContent: 'center', lineHeight: 1,
                          }}>✓</span>
                        )}
                      </span>
                    </td>
                    <td><span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-dim)' }}>{row[6]}</span></td>
                  </tr>
                ))}
                {/* + Row */}
                <tr>
                  <td className="row-num" colSpan={TABLE_HEADERS.length + 1} style={{ textAlign: 'left', paddingLeft: 14, color: 'var(--text-muted)', fontSize: 12 }}>
                    + New row
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Footer summary */}
          <div style={{
            marginTop: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            fontSize: 11.5, color: 'var(--text-muted)',
          }}>
            <div style={{ display: 'flex', gap: 16, fontFamily: 'var(--font-mono)' }}>
              <span>count · 12</span>
              <span>sum(mentions) · 74</span>
              <span>open · 6</span>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <span className="stash-chip"><span className="dot" />v0 launch prep</span>
              <span className="stash-chip"><span className="dot" />Customer interviews · oct</span>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

window.TableScreen = TableScreen;
