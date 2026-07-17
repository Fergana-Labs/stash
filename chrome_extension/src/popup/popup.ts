// Popup: connect once, then save the current tab / all tabs, and see the
// status of the background pollers (ChatGPT, Claude, Instagram, X) with a
// "Sync now" for each. Saving is otherwise automatic.

const app = document.getElementById('app')!;

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
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

async function send(message: any): Promise<any> {
  return chrome.runtime.sendMessage(message);
}

const PLATFORMS: { key: string; label: string }[] = [
  { key: 'chatgpt', label: 'ChatGPT' },
  { key: 'claude', label: 'Claude' },
  { key: 'instagram', label: 'Instagram' },
];

async function render(): Promise<void> {
  const status = await send({ type: 'GET_STATUS' });
  app.replaceChildren();
  app.classList.remove('muted');

  if (!status.connected) {
    app.append(
      el('p', { className: 'muted' }, [
        'Save webpages, PDFs, and your ChatGPT / Claude / Instagram / X activity to Stash. Connect once to start.',
      ]),
      el('div', { className: 'row' }, [
        el('button', {
          textContent: 'Connect to Stash',
          onclick: async () => {
            app.replaceChildren(
              el('p', { className: 'muted' }, ['Finish signing in in the tab that just opened…'])
            );
            await send({ type: 'CONNECT' });
            await render();
          },
        }),
      ])
    );
    app.append(renderAdvanced(status));
    return;
  }

  app.append(el('p', {}, ['Connected as ', el('strong', { textContent: status.username || '?' })]));

  // Save actions: this tab, then all tabs right below it.
  app.append(
    el('div', { className: 'row' }, [
      el('button', {
        textContent: 'Save this tab',
        onclick: async () => {
          await send({ type: 'CLIP_TAB' });
          setTimeout(() => void render(), 1200);
        },
      }),
    ]),
    el('div', { className: 'row' }, [
      el('button', {
        className: 'outline',
        textContent: 'Save all open tabs',
        onclick: async () => {
          const result = await send({ type: 'CLIP_ALL_TABS' });
          if (!result?.ok) await render();
        },
      }),
    ])
  );

  if (status.lastError) {
    app.append(el('div', { className: 'error', textContent: status.lastError }));
  }

  app.append(await renderSources());
  app.append(renderAdvanced(status));

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

// The background pollers: each shows whether you're signed in to the site and
// when it last synced, with a Sync-now button.
async function renderSources(): Promise<HTMLElement> {
  const section = el('div', { className: 'sources' }, [
    el('div', { className: 'section-label' }, ['Sources']),
  ]);
  const statuses = await send({ type: 'PLATFORM_STATUS' });

  for (const { key, label } of PLATFORMS) {
    const s = statuses?.[key] || { connected: false, lastSyncAt: null };
    const detail = !s.connected
      ? 'Not connected — sign in on the site'
      : s.lastSyncAt
        ? `Synced ${timeAgo(s.lastSyncAt)}`
        : 'Connected';

    const syncBtn = el('button', {
      className: 'secondary sync-now',
      textContent: 'Sync now',
      disabled: !s.connected,
      onclick: async () => {
        syncBtn.textContent = 'Syncing…';
        syncBtn.disabled = true;
        await send({ type: 'SYNC_NOW', platform: key });
        setTimeout(() => void render(), 1500);
      },
    });

    section.append(
      el('div', { className: 'source-row' }, [
        el('span', { className: `dot ${s.connected ? 'on' : 'off'}` }),
        el('div', { className: 'source-meta' }, [
          el('div', { className: 'source-name' }, [label]),
          el('div', { className: 'source-detail muted' }, [detail]),
        ]),
        syncBtn,
      ])
    );
  }
  return section;
}

// Advanced: import a bookmarks.html export + the Stash API URL. Tucked away.
function renderAdvanced(status: any): HTMLElement {
  const progressRow = el('div', { className: 'row muted' });

  async function showProgress(importId: string): Promise<void> {
    const result = await send({ type: 'IMPORT_PROGRESS', id: importId });
    if (!result?.ok) {
      progressRow.textContent = result?.error || 'Progress check failed';
      return;
    }
    const p = result.progress;
    progressRow.textContent = `Import: ${p.done}/${p.total} done, ${p.failed} failed, ${p.pending} pending`;
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

  const apiBaseInput = el('input', { value: status.apiBase, spellcheck: false });

  const details = el('details', {}, [
    el('summary', { textContent: 'Advanced' }),
    el('div', { className: 'row' }, [
      el('label', { textContent: 'Import a bookmarks.html export' }),
      fileInput,
    ]),
    progressRow,
    el('div', { className: 'row' }, [
      el('label', { textContent: 'Stash API URL' }),
      apiBaseInput,
      el('button', {
        textContent: 'Save & reconnect',
        onclick: async () => {
          await send({ type: 'SET_API_BASE', apiBase: apiBaseInput.value.trim() });
          await render();
        },
      }),
    ]),
  ]);

  if (status.lastImport?.id) void showProgress(status.lastImport.id);
  return details;
}

void render();
