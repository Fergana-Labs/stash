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

// Confirmation for the save that just happened, rendered above the buttons
// until the next action replaces it. Saving used to report itself only
// through a 3s badge flash on the toolbar icon — which the open popup covers.
let confirmation: {
  headline: string;
  detail?: string;
  href?: string;
  pending?: boolean;
} | null = null;
let actionError: string | null = null;
// A save in flight. Kept across re-renders so the acknowledgement can paint
// before the request returns without leaving a live button behind it.
let busy = false;

async function saveThisTab(since: number): Promise<void> {
  actionError = null;
  busy = true;
  confirmation = { headline: 'Saving this tab…', pending: true };
  await render();
  await send({ type: 'CLIP_TAB' });

  const outcome = await waitForClip(since);
  busy = false;
  confirmation = null;
  if (outcome.state === 'saved') {
    confirmation = { headline: `Saved "${outcome.clip.title}"`, href: outcome.clip.appUrl };
  } else if (outcome.state === 'slow') {
    actionError = 'Still saving — this page is taking a while. It will finish in the background.';
  }
  // 'failed' needs nothing: clipFailed already wrote a clip error, and the
  // error list below renders it.
  await render();
}

// The clip lands after CLIP_TAB has already returned — the injected clipper
// posts the page back to the worker, which then uploads it. So watch storage
// for whichever terminal state arrives first.
type ClipOutcome = { state: 'saved'; clip: any } | { state: 'failed' } | { state: 'slow' };

async function waitForClip(since: number): Promise<ClipOutcome> {
  for (let attempt = 0; attempt < 25; attempt++) {
    await new Promise((r) => setTimeout(r, 400));
    const status = await send({ type: 'GET_STATUS' });
    if ((status.lastClip?.at ?? 0) > since) return { state: 'saved', clip: status.lastClip };
    const failed = (status.errors ?? []).some((e: any) => e.surface === 'clip' && e.at > since);
    if (failed) return { state: 'failed' };
  }
  return { state: 'slow' };
}

async function saveAllTabs(count: number): Promise<void> {
  actionError = null;
  // Acknowledge before the request finishes. Saving 200 tabs means a dedupe
  // query and a bulk insert, and a button that just sits there reads as a
  // click that didn't land.
  busy = true;
  confirmation = {
    headline: `Saving ${count} tab${count === 1 ? '' : 's'}…`,
    detail: 'You can close this popup — it keeps going without you.',
    pending: true,
  };
  await render();

  const result = await send({ type: 'CLIP_ALL_TABS' });
  busy = false;
  if (!result.ok) {
    actionError = result.error;
    await render();
    return;
  }
  if (result.total === 0) {
    // Every tab was a duplicate. Nothing was saved and nothing is downloading,
    // so neither a count nor a progress promise belongs here.
    confirmation = {
      headline: 'Nothing new to save',
      detail: `All ${result.skipped} open tabs are already in your Stash.`,
    };
  } else {
    // Two separate facts, and they finish at different times: the links are
    // saved now, the page contents are still downloading.
    const links = `${result.total} link${result.total === 1 ? '' : 's'}`;
    confirmation = {
      headline: `${links} saved`,
      detail:
        `Downloading page contents now.` +
        (result.skipped > 0 ? ` ${result.skipped} were already in your Stash.` : ''),
    };
  }
  await render();
}

function renderConfirmation(): HTMLElement {
  const c = confirmation!;
  // The tick is a claim. It only goes on once the save has actually landed.
  const box = el('div', { className: c.pending ? 'saved pending' : 'saved' }, [
    el('div', { className: 'headline' }, [c.pending ? c.headline : `✓ ${c.headline}`]),
  ]);
  if (c.detail) box.append(el('div', { className: 'detail' }, [c.detail]));
  if (c.href) {
    box.append(
      el('div', { className: 'detail' }, [
        el('a', { href: c.href, target: '_blank', textContent: 'View in Stash' }),
      ])
    );
  }
  return box;
}

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
  const { count } = await send({ type: 'CLIPPABLE_TABS' });
  const saveTab = el('button', {
    textContent: 'Save this tab',
    disabled: busy,
    onclick: () => void saveThisTab(status.lastClip?.at ?? 0),
  });
  const saveAll = el('button', {
    className: 'outline',
    // The count on the button face is the whole promise of the action: you
    // know what you're about to save before you commit to it.
    textContent: `Save all ${count} open tab${count === 1 ? '' : 's'}`,
    disabled: busy || count === 0,
    onclick: () => void saveAllTabs(count),
  });
  app.append(el('div', { className: 'row' }, [saveTab]), el('div', { className: 'row' }, [saveAll]));

  if (confirmation) {
    app.append(renderConfirmation());
  } else if (status.lastClip) {
    app.append(
      el('div', { className: 'last-clip' }, [
        `Last saved: ${status.lastClip.title} · ${timeAgo(status.lastClip.at)}`,
      ])
    );
  }

  if (actionError) app.append(el('div', { className: 'error', textContent: actionError }));
  for (const err of status.errors ?? []) {
    app.append(el('div', { className: 'error', textContent: err.message }));
  }

  // A running bulk import is the thing the user most wants to see — top
  // level, not tucked in Advanced (its file input stays there). Once it has
  // finished and announced itself, the row has nothing left to say and would
  // otherwise sit there until the next import replaced it.
  if (status.lastImport?.id && !status.lastImport.doneNotified) {
    const progressRow = el('div', { className: 'row muted' });
    app.append(progressRow);
    void showImportProgress(status.lastImport.id, progressRow);
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

async function showImportProgress(importId: string, row: HTMLElement): Promise<void> {
  const result = await send({ type: 'IMPORT_PROGRESS', id: importId });
  if (!result?.ok) {
    row.textContent = result?.error || 'Progress check failed';
    return;
  }
  const p = result.progress;
  const running = p.pending > 0 || p.needs_client > 0;
  // The links are already saved by the time this row exists; every number
  // here is about the page contents, so the label says so.
  const parts = [`${p.done} of ${p.total} downloaded`];
  if (p.link_only > 0) parts.push(`${p.link_only} kept as link-only`);
  if (p.needs_client > 0) parts.push(`${p.needs_client} via this browser`);
  if (p.pending > 0) parts.push(`${p.pending} pending`);
  row.textContent = `Page contents: ${parts.join(', ')}`;
  if (running) setTimeout(() => void showImportProgress(importId, row), 2000);
}

// Advanced: import a bookmarks.html export + the Stash API URL. Tucked away.
function renderAdvanced(status: any): HTMLElement {
  const progressRow = el('div', { className: 'row muted' });

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
    void showImportProgress(result.importId, progressRow);
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

  return details;
}

void render();
