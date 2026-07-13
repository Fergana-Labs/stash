// Popup: one-time connect + folder choice + sync status. Syncing itself
// is fully automatic and never needs this UI.

const app = document.getElementById('app')!;

function appBase(apiBase: string): string {
  const api = apiBase.replace(/\/$/, '');
  if (api === 'https://api.joinstash.ai') return 'https://joinstash.ai';
  if (api.includes('localhost') || api.includes('127.0.0.1')) return api.replace(':3456', ':3457');
  return api;
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> = {},
  children: (HTMLElement | string)[] = []
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const child of children) node.append(child);
  return node;
}

function timeAgo(ts: number): string {
  const mins = Math.round((Date.now() - ts) / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  return `${Math.round(mins / 60)}h ago`;
}

async function send(message: any): Promise<any> {
  return chrome.runtime.sendMessage(message);
}

async function render(): Promise<void> {
  const status = await send({ type: 'GET_STATUS' });
  app.replaceChildren();
  app.classList.remove('muted');

  if (!status.connected) {
    app.append(
      el('p', { className: 'muted' }, [
        'Open conversations on chatgpt.com or claude.ai are saved to Stash automatically. Connect once to start.',
      ]),
      el('div', { className: 'row' }, [
        el('button', {
          textContent: 'Connect to Stash',
          onclick: async () => {
            app.replaceChildren(el('p', { className: 'muted' }, ['Finish signing in in the tab that just opened…']));
            await send({ type: 'CONNECT' });
            await render();
          },
        }),
      ])
    );
  } else {
    const folderSelect = el('select', {
      onchange: async () => {
        const picked = status.folders.find((f: any) => f.id === folderSelect.value);
        await send({ type: 'SET_FOLDER', id: picked.id, name: picked.name });
      },
    });
    for (const f of status.folders) {
      folderSelect.append(
        el('option', { value: f.id, textContent: f.name, selected: f.id === status.folderId })
      );
    }

    app.append(
      el('p', {}, ['Connected as ', el('strong', { textContent: status.username || '?' })]),
      el('div', { className: 'row' }, [
        el('button', {
          textContent: 'Save this page to Stash',
          onclick: async () => {
            const result = await send({ type: 'CLIP_TAB' });
            if (result?.ok) {
              // Give the injected clipper a beat to report back, then re-render
              // so lastClip / lastError shows.
              setTimeout(() => void render(), 1200);
            } else {
              await render();
            }
          },
        }),
      ]),
      el('div', { className: 'row' }, [el('label', { textContent: 'Session folder' }), folderSelect])
    );

    if (status.lastClip) {
      const clipChildren: (HTMLElement | string)[] = [
        `Clipped “${status.lastClip.title}” ${timeAgo(status.lastClip.at)}`,
      ];
      if (status.lastClip.appUrl) {
        clipChildren.push(
          ' — ',
          el('a', { href: status.lastClip.appUrl, target: '_blank', textContent: 'view clip' })
        );
      } else if (status.lastClip.importId) {
        clipChildren.push(' — processing on the server');
      }
      app.append(el('p', { className: 'row muted' }, clipChildren));
    }

    if (status.lastSync) {
      app.append(
        el('p', { className: 'row muted' }, [
          `Last synced “${status.lastSync.title}” ${timeAgo(status.lastSync.at)} — `,
          el('a', {
            href: `${appBase(status.apiBase)}/sessions/${status.lastSync.sessionId}`,
            target: '_blank',
            textContent: 'view session',
          }),
        ])
      );
    }

    if (status.lastError) {
      app.append(el('div', { className: 'error', textContent: status.lastError }));
    }

    app.append(renderImports(status));

    app.append(
      el('div', { className: 'row' }, [
        el('button', {
          className: 'secondary',
          textContent: 'Disconnect',
          onclick: async () => {
            await send({ type: 'DISCONNECT' });
            await render();
          },
        }),
      ])
    );
  }

  const apiBaseInput = el('input', { value: status.apiBase, spellcheck: false });
  app.append(
    el('details', {}, [
      el('summary', { textContent: 'Advanced' }),
      el('div', { className: 'row' }, [
        el('label', { textContent: 'Stash API URL' }),
        apiBaseInput,
        el('div', { className: 'row' }, [
          el('button', {
            textContent: 'Save & reconnect',
            onclick: async () => {
              await send({ type: 'SET_API_BASE', apiBase: apiBaseInput.value.trim() });
              await render();
            },
          }),
        ]),
      ]),
    ])
  );
}

// Bulk imports: clip every open tab, or upload a browser bookmarks.html
// export. Both run in the background worker; this section just triggers
// them and polls batch progress.
function renderImports(status: any): HTMLElement {
  const section = el('details', {}, [el('summary', { textContent: 'Import' })]);
  const progressRow = el('div', { className: 'row muted' });

  async function showProgress(importId: string): Promise<void> {
    const result = await send({ type: 'IMPORT_PROGRESS', id: importId });
    if (!result?.ok) {
      progressRow.textContent = result?.error || 'Progress check failed';
      return;
    }
    const p = result.progress;
    progressRow.textContent = `${p.kind} import: ${p.done}/${p.total} done, ${p.failed} failed, ${p.pending} pending`;
    if (p.pending > 0) setTimeout(() => void showProgress(importId), 2000);
  }

  const fileInput = el('input', { type: 'file', accept: '.html' });
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    progressRow.textContent = 'Uploading bookmarks…';
    const result = await send({
      type: 'IMPORT_BOOKMARKS',
      name: file.name,
      content: await file.text(),
    });
    if (!result?.ok) {
      progressRow.textContent = result?.error || 'Import failed';
      return;
    }
    void showProgress(result.importId);
  });

  section.append(
    el('div', { className: 'row' }, [
      el('button', {
        textContent: 'Clip all open tabs',
        onclick: async () => {
          progressRow.textContent = 'Starting…';
          const result = await send({ type: 'CLIP_ALL_TABS' });
          if (!result?.ok) {
            progressRow.textContent = result?.error || 'Clip-all-tabs failed';
            return;
          }
          void showProgress(result.importId);
        },
      }),
    ]),
    el('div', { className: 'row' }, [
      el('label', { textContent: 'Import a bookmarks.html export' }),
      fileInput,
    ]),
    progressRow
  );

  if (status.lastImport?.id) void showProgress(status.lastImport.id);
  return section;
}

void render();
