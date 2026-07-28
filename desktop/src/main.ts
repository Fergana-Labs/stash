import { invoke } from "@tauri-apps/api/core";
import { disable, enable, isEnabled } from "@tauri-apps/plugin-autostart";

interface Checks {
  signed_in: boolean;
  username: string | null;
  base_url: string;
  cli_installed: boolean;
  cli_version: string | null;
  claude_installed: boolean;
  plugin_installed: boolean;
}

const $ = (id: string) => document.getElementById(id)!;

function el(tag: string, className: string, text?: string): HTMLElement {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function statusItem(
  state: "ok" | "warn" | "bad" | "off",
  label: string,
  detail: string,
): HTMLLIElement {
  const li = document.createElement("li");
  li.append(el("span", `dot ${state}`));
  li.append(el("span", "item-label", label));
  li.append(el("span", "spacer"));
  const detailEl = el("span", "item-detail");
  detailEl.innerHTML = detail;
  li.append(detailEl);
  return li;
}

function showError(id: string, message: string | null) {
  const node = $(id);
  node.hidden = message === null;
  node.textContent = message ?? "";
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString();
}

// ---------------------------------------------------------------------------
// Getting set up
// ---------------------------------------------------------------------------

async function renderChecklist() {
  showError("setup-error", null);
  let checks: Checks;
  try {
    checks = await invoke<Checks>("run_checks");
  } catch (e) {
    showError("setup-error", String(e));
    return;
  }

  $("account-chip").textContent = checks.signed_in
    ? (checks.username || "signed in")
    : "not signed in";

  const list = $("checklist");
  list.replaceChildren();

  const signin = statusItem(
    checks.signed_in ? "ok" : "bad",
    "Signed in to Stash",
    checks.signed_in ? checks.base_url : "",
  );
  if (!checks.signed_in) {
    const btn = el("button", "btn", "Sign in") as HTMLButtonElement;
    btn.addEventListener("click", () => signIn(btn));
    signin.append(btn);
  }
  list.append(signin);

  list.append(
    statusItem(
      checks.cli_installed ? "ok" : "bad",
      "stash CLI installed",
      checks.cli_installed
        ? checks.cli_version ?? ""
        : "Install: <code>uv tool install stashai</code>",
    ),
  );
  list.append(
    statusItem(
      checks.claude_installed ? "ok" : "bad",
      "Claude Code installed",
      checks.claude_installed
        ? ""
        : "Install: <code>npm install -g @anthropic-ai/claude-code</code>",
    ),
  );
  list.append(
    statusItem(
      checks.plugin_installed ? "ok" : "bad",
      "Stash plugin for Claude Code",
      checks.plugin_installed ? "" : "Run <code>stash signin</code> to install it",
    ),
  );
}

async function signIn(btn: HTMLButtonElement) {
  btn.disabled = true;
  btn.textContent = "Waiting for browser…";
  try {
    const { session_id } = await invoke<{ session_id: string }>("signin_start");
    for (let i = 0; i < 120; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const { status } = await invoke<{ status: string }>("signin_poll", {
        sessionId: session_id,
      });
      if (status === "complete") {
        await refreshAll();
        return;
      }
    }
    throw new Error("Sign-in timed out after 120s");
  } catch (e) {
    showError("setup-error", String(e));
    btn.disabled = false;
    btn.textContent = "Sign in";
  }
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

async function renderHealth() {
  showError("health-error", null);

  const backendRow = $("backend-health");
  backendRow.replaceChildren();
  try {
    const healthy = await invoke<boolean>("backend_health");
    backendRow.append(el("span", `dot ${healthy ? "ok" : "bad"}`));
    backendRow.append(
      el("span", "item-label", healthy ? "Backend reachable" : "Backend unreachable"),
    );
  } catch (e) {
    backendRow.append(el("span", "dot bad"));
    backendRow.append(el("span", "item-label", `Backend unreachable — ${e}`));
  }

  const integrations = $("integrations");
  const sources = $("sources");
  integrations.replaceChildren();
  sources.replaceChildren();
  try {
    const [intsBody, sourcesBody] = await Promise.all([
      invoke<{ providers: any[] }>("list_integrations"),
      invoke<{ sources: any[] }>("list_sources"),
    ]);

    const connected = intsBody.providers.filter((p) => p.connected || p.disconnected);
    if (connected.length === 0) {
      integrations.append(statusItem("off", "No integrations connected", ""));
    }
    for (const p of connected) {
      const needsReconnect = (p.accounts ?? []).some((a: any) => a.needs_reconnect);
      const state = p.disconnected ? "off" : needsReconnect ? "warn" : "ok";
      const detail = p.disconnected
        ? "disconnected"
        : needsReconnect
          ? "needs reconnect"
          : (p.account_email ?? "connected");
      integrations.append(statusItem(state, p.display_name, detail));
    }

    for (const s of sourcesBody.sources) {
      if (!("sync_status" in s)) continue; // native sources have no sync state
      const state =
        s.sync_error ? "bad" : s.sync_status === "syncing" ? "warn" : "ok";
      const detail =
        s.sync_error ?? `${s.sync_status ?? "idle"} · synced ${fmtTime(s.last_synced_at)}`;
      sources.append(statusItem(state, s.display_name, detail));
    }
    if (!sources.hasChildNodes()) {
      sources.append(statusItem("off", "No connected sources", ""));
    }
  } catch (e) {
    showError("health-error", String(e));
  }
}

// ---------------------------------------------------------------------------
// Memory curator (server-side)
// ---------------------------------------------------------------------------

async function renderMemory() {
  const box = $("memory-status");
  box.replaceChildren();
  try {
    const curator = await invoke<any>("curator_status");
    if (!curator) {
      box.append(el("p", "muted", "No Memory curator on this account yet."));
      return;
    }
    const list = el("ul", "statuslist");
    list.append(
      statusItem(
        curator.last_run_error ? "bad" : curator.last_run_at ? "ok" : "off",
        "Last run",
        curator.last_run_error ?? fmtTime(curator.last_run_at),
      ),
    );
    list.append(statusItem("off", "Curated through", fmtTime(curator.curated_through)));
    list.append(
      statusItem("off", "Runs this month", String(curator.month_run_count ?? 0)),
    );
    box.append(list);
  } catch (e) {
    box.append(el("p", "error", String(e)));
  }
}

async function recomputeMemory() {
  const btn = $("recompute-btn") as HTMLButtonElement;
  const msg = $("memory-msg");
  btn.disabled = true;
  msg.textContent = "Starting…";
  try {
    await invoke("recompute_memory");
    msg.textContent = "Curation started.";
  } catch (e) {
    msg.textContent = String(e);
  } finally {
    btn.disabled = false;
    await renderMemory();
  }
}

// ---------------------------------------------------------------------------
// Local curator
// ---------------------------------------------------------------------------

async function renderLocal() {
  showError("local-error", null);
  try {
    const status = await invoke<any>("curator_local_status");

    ($("local-enabled") as HTMLInputElement).checked = status.enabled;
    ($("local-interval") as HTMLSelectElement).value = String(status.interval_hours);

    const box = $("local-status");
    box.replaceChildren();
    const list = el("ul", "statuslist");
    if (status.running) {
      list.append(statusItem("warn", "Curation run in progress", ""));
    }
    const last = status.last_run;
    list.append(
      statusItem(
        !last ? "off" : last.exit_code === 0 ? "ok" : "bad",
        "Last run",
        !last
          ? "never"
          : `${fmtTime(last.finished_at)} · exit ${last.exit_code ?? "?"}`,
      ),
    );
    box.append(list);

    const log = $("local-log");
    log.hidden = !status.log_tail;
    log.textContent = status.log_tail ?? "";
  } catch (e) {
    showError("local-error", String(e));
  }
}

async function runLocalNow() {
  const btn = $("local-run-btn") as HTMLButtonElement;
  btn.disabled = true;
  try {
    await invoke("curator_run_now");
  } catch (e) {
    showError("local-error", String(e));
  } finally {
    btn.disabled = false;
    await renderLocal();
  }
}

async function renderAutostart() {
  try {
    ($("autostart-toggle") as HTMLInputElement).checked = await isEnabled();
  } catch {
    // Autostart is unavailable in `tauri dev` on some platforms; leave unchecked.
  }
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

async function refreshAll() {
  await Promise.all([renderChecklist(), renderHealth(), renderMemory(), renderLocal()]);
}

window.addEventListener("DOMContentLoaded", () => {
  $("refresh-btn").addEventListener("click", refreshAll);
  $("recompute-btn").addEventListener("click", recomputeMemory);
  $("local-run-btn").addEventListener("click", runLocalNow);

  $("local-enabled").addEventListener("change", async (e) => {
    const enabled = (e.target as HTMLInputElement).checked;
    await invoke("curator_set_enabled", { enabled });
  });
  $("local-interval").addEventListener("change", async (e) => {
    const hours = Number((e.target as HTMLSelectElement).value);
    await invoke("curator_set_interval", { hours });
    await renderLocal();
  });
  $("autostart-toggle").addEventListener("change", async (e) => {
    const on = (e.target as HTMLInputElement).checked;
    try {
      if (on) await enable();
      else await disable();
    } catch (err) {
      showError("local-error", String(err));
      await renderAutostart();
    }
  });

  refreshAll();
  renderAutostart();
  setInterval(refreshAll, 60_000);
});
