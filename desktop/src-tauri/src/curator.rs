//! The local curator: runs `claude -p <prompt>` headlessly on this machine so
//! curation happens with the user's own credentials and MCP connectors — the
//! knowledge base never requires Stash's cloud to see private sources.
//!
//! The prompt is served by the backend (`GET /api/v1/me/local-curator-prompt`)
//! and fetched fresh before every run, so prompt iterations reach every
//! install without an app release. State lives in ~/.stash/curator/:
//! config.json (enabled / interval / extra claude args), runs.jsonl (one
//! record per completed run), and per-run logs. A scheduler thread triggers a
//! run when the last successful one is older than the configured interval
//! (failures retry after a short delay instead) — which also covers "the
//! laptop was closed at the scheduled time": the run fires as overdue on
//! next launch.

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};

static RUNNING: AtomicBool = AtomicBool::new(false);

/// Harnesses the curator can run through, in auto-pick priority order.
const AGENT_PRIORITY: [&str; 3] = ["claude", "openclaw", "hermes"];

#[derive(Debug, Serialize, Deserialize)]
pub struct LocalConfig {
    pub enabled: bool,
    pub interval_hours: u64,
    /// "auto" picks the first installed harness from AGENT_PRIORITY; or name
    /// one explicitly ("claude" | "openclaw" | "hermes").
    pub agent: String,
    /// Claude-only: base permission rules for the headless run. The user's
    /// MCP servers are discovered and appended at spawn time — see
    /// `mcp_allow_rules`. OpenClaw and Hermes have no per-tool grant flag;
    /// their runs use the harness's own configured permissions.
    pub allowed_tools: Vec<String>,
}

fn state_dir() -> PathBuf {
    dirs::home_dir()
        .expect("no home directory")
        .join(".stash/curator")
}

fn config_path() -> PathBuf {
    state_dir().join("config.json")
}

fn runs_path() -> PathBuf {
    state_dir().join("runs.jsonl")
}

fn logs_dir() -> PathBuf {
    state_dir().join("logs")
}

pub fn ensure_state_files() -> Result<(), std::io::Error> {
    std::fs::create_dir_all(logs_dir())?;
    if !config_path().exists() {
        // Disabled until the user flips the switch in the UI: a fresh install
        // must not silently start spending tokens on headless agent runs.
        // No Write grant: the curator maintains the wiki through `stash files
        // add-page/edit-page` and must not be able to modify local files —
        // including this config, which governs future runs' permissions.
        let default = LocalConfig {
            enabled: false,
            interval_hours: 6,
            agent: "auto".into(),
            allowed_tools: vec!["Bash(stash:*)".into()],
        };
        write_config(&default).map_err(std::io::Error::other)?;
    }
    Ok(())
}

fn load_local_config() -> Result<LocalConfig, String> {
    let path = config_path();
    let raw = std::fs::read_to_string(&path)
        .map_err(|e| format!("read {}: {e}", path.display()))?;
    serde_json::from_str(&raw).map_err(|e| format!("parse {}: {e}", path.display()))
}

fn write_config(cfg: &LocalConfig) -> Result<(), String> {
    let pretty = serde_json::to_string_pretty(cfg).expect("serialize curator config");
    std::fs::write(config_path(), pretty + "\n").map_err(|e| e.to_string())
}

fn read_runs() -> Vec<Value> {
    let Ok(raw) = std::fs::read_to_string(runs_path()) else {
        return Vec::new();
    };
    raw.lines()
        .filter_map(|l| serde_json::from_str(l).ok())
        .collect()
}

fn last_run() -> Option<Value> {
    read_runs().pop()
}

#[tauri::command]
pub fn curator_local_status() -> Result<Value, String> {
    let cfg = load_local_config()?;
    let last = last_run();
    let log_tail = last
        .as_ref()
        .and_then(|r| r["log"].as_str())
        .and_then(|p| std::fs::read_to_string(p).ok())
        .map(|s| {
            let lines: Vec<&str> = s.lines().collect();
            let start = lines.len().saturating_sub(30);
            lines[start..].join("\n")
        });
    let agent = resolve_agent(&cfg);
    Ok(json!({
        "enabled": cfg.enabled,
        "interval_hours": cfg.interval_hours,
        "agent": agent.as_deref().ok(),
        "agent_error": agent.as_deref().err(),
        "running": RUNNING.load(Ordering::SeqCst),
        "last_run": last,
        "log_tail": log_tail,
    }))
}

/// spawn_run does blocking work (the prompt fetch), so keep it off the
/// webview's thread.
#[tauri::command]
pub async fn curator_run_now() -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(spawn_run)
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
pub fn curator_set_enabled(enabled: bool) -> Result<(), String> {
    let mut cfg = load_local_config()?;
    cfg.enabled = enabled;
    write_config(&cfg)
}

#[tauri::command]
pub fn curator_set_interval(hours: u64) -> Result<(), String> {
    if hours == 0 {
        return Err("interval must be at least 1 hour".into());
    }
    let mut cfg = load_local_config()?;
    cfg.interval_hours = hours;
    write_config(&cfg)
}

/// Start a curation run. Refuses if one is already in flight.
pub fn spawn_run() -> Result<(), String> {
    if RUNNING.swap(true, Ordering::SeqCst) {
        return Err("Curator is already running".into());
    }
    let result = start_child();
    if result.is_err() {
        RUNNING.store(false, Ordering::SeqCst);
    }
    result
}

/// Fetched fresh before every run — no local copy, no stale-prompt codepath.
fn fetch_prompt() -> Result<String, String> {
    let cfg = crate::config::load()?;
    let key = cfg.api_key.ok_or("Not signed in")?;
    let resp = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .expect("build http client")
        .get(format!("{}/api/v1/me/local-curator-prompt", cfg.base_url))
        .bearer_auth(&key)
        .send()
        .map_err(|e| format!("fetch curator prompt: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!(
            "fetch curator prompt: HTTP {}",
            resp.status().as_u16()
        ));
    }
    let body: Value = resp.json().map_err(|e| format!("fetch curator prompt: {e}"))?;
    body["prompt"]
        .as_str()
        .filter(|p| !p.is_empty())
        .map(str::to_string)
        .ok_or_else(|| "curator prompt response missing prompt".to_string())
}

/// One `mcp__<server>` allow rule per MCP server in the user's Claude config.
/// Curation is supposed to read through the user's connectors, and a headless
/// run denies any tool without an allow rule — there is no global MCP
/// wildcard, so the grant has to be built per server, per run.
fn mcp_allow_rules() -> Vec<String> {
    let path = dirs::home_dir()
        .expect("no home directory")
        .join(".claude.json");
    let Ok(raw) = std::fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(v) = serde_json::from_str::<Value>(&raw) else {
        return Vec::new();
    };
    let Some(servers) = v["mcpServers"].as_object() else {
        return Vec::new();
    };
    servers.keys().map(|name| format!("mcp__{name}")).collect()
}

/// The watermark the prompt's incremental pass filters against. The server
/// prompt tells the agent what to do with it; the app only knows *when*.
fn runtime_context() -> String {
    let last_success = read_runs()
        .iter()
        .rev()
        .find(|r| r["exit_code"] == 0)
        .and_then(|r| r["finished_at"].as_str().map(str::to_string));
    match last_success {
        Some(ts) => format!(
            "\n\n## Runtime context\n\nYour last successful curation run finished at {ts}. \
             Treat material newer than that as new; earlier runs already covered the rest."
        ),
        None => "\n\n## Runtime context\n\nThis is the first curation run on this machine. \
                 Survey roughly the last week of activity; do not ingest deep history."
            .to_string(),
    }
}

fn find_on_path(binary: &str) -> bool {
    let Ok(path) = std::env::var("PATH") else {
        return false;
    };
    std::env::split_paths(&path).any(|dir| dir.join(binary).is_file())
}

/// The harness this run will use. "auto" takes the first installed harness
/// in priority order; a named agent must actually be installed.
pub fn resolve_agent(cfg: &LocalConfig) -> Result<String, String> {
    if cfg.agent != "auto" {
        if !AGENT_PRIORITY.contains(&cfg.agent.as_str()) {
            return Err(format!(
                "unsupported curator agent '{}' (supported: {})",
                cfg.agent,
                AGENT_PRIORITY.join(", ")
            ));
        }
        if !find_on_path(&cfg.agent) {
            return Err(format!("configured curator agent '{}' is not installed", cfg.agent));
        }
        return Ok(cfg.agent.clone());
    }
    AGENT_PRIORITY
        .iter()
        .find(|b| find_on_path(b))
        .map(|b| b.to_string())
        .ok_or_else(|| {
            format!(
                "no supported agent harness installed (looked for: {})",
                AGENT_PRIORITY.join(", ")
            )
        })
}

fn build_command(agent: &str, prompt: &str, cfg: &LocalConfig) -> Command {
    let mut cmd = Command::new(agent);
    match agent {
        "claude" => {
            let mut rules = cfg.allowed_tools.clone();
            rules.extend(mcp_allow_rules());
            cmd.arg("-p")
                .arg(prompt)
                .arg("--allowedTools")
                .arg(rules.join(","));
        }
        // --deliver defaults to false: the reply never leaves the machine
        // for a messaging channel. --local runs the embedded agent; a
        // dedicated session id keeps curation out of their chat sessions
        // (and is required — openclaw refuses a turn without a session).
        "openclaw" => {
            cmd.args([
                "agent",
                "--local",
                "--session-id",
                "stash-curator",
                "--timeout",
                "3600",
                "-m",
            ])
            .arg(prompt);
        }
        // -z is Hermes's documented one-shot mode; HERMES_ACCEPT_HOOKS
        // pre-approves shell hooks so an unattended run can't stall on an
        // approval prompt.
        "hermes" => {
            cmd.arg("-z").arg(prompt).env("HERMES_ACCEPT_HOOKS", "1");
        }
        _ => unreachable!("resolve_agent validated the harness"),
    }
    // The knowledge base is per-person: pin every stash call in the run to
    // the personal scope, even when config points at a workspace.
    cmd.env("STASH_SCOPE", "");
    cmd
}

fn start_child() -> Result<(), String> {
    let cfg = load_local_config()?;
    let agent = resolve_agent(&cfg)?;
    let prompt = fetch_prompt()? + &runtime_context();
    let started = chrono::Utc::now();
    let log_path = logs_dir().join(format!("{}.log", started.format("%Y%m%dT%H%M%SZ")));
    let log = std::fs::File::create(&log_path).map_err(|e| e.to_string())?;
    let log_err = log.try_clone().map_err(|e| e.to_string())?;

    let mut cmd = build_command(&agent, &prompt, &cfg);
    let mut child = cmd
        .stdin(Stdio::null())
        .stdout(log)
        .stderr(log_err)
        .spawn()
        .map_err(|e| format!("spawn {agent}: {e}"))?;

    std::thread::spawn(move || {
        let status = child.wait();
        let record = json!({
            "started_at": started.to_rfc3339(),
            "finished_at": chrono::Utc::now().to_rfc3339(),
            "exit_code": status.ok().and_then(|s| s.code()),
            "agent": agent,
            "log": log_path.display().to_string(),
        });
        if let Ok(mut f) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(runs_path())
        {
            let _ = writeln!(f, "{record}");
        }
        RUNNING.store(false, Ordering::SeqCst);
    });
    Ok(())
}

pub fn start_scheduler() {
    std::thread::spawn(|| loop {
        std::thread::sleep(std::time::Duration::from_secs(60));
        if RUNNING.load(Ordering::SeqCst) {
            continue;
        }
        let cfg = match load_local_config() {
            Ok(cfg) => cfg,
            Err(e) => {
                eprintln!("curator scheduler: {e}");
                continue;
            }
        };
        if !cfg.enabled || !due(cfg.interval_hours) {
            continue;
        }
        if let Err(e) = spawn_run() {
            eprintln!("curator scheduler: {e}");
        }
    });
}

/// After a failed run (lid closed mid-run, network death), retry after this
/// long instead of waiting out the full interval — a sleepy laptop should
/// cost minutes of coverage, not a day. It still debounces a permanently
/// broken setup out of crash-looping the agent every scheduler tick.
const RETRY_DELAY_MINUTES: i64 = 30;

/// The interval is measured from the last *successful* run; any run at all
/// (including failures) imposes the shorter retry delay.
fn due(interval_hours: u64) -> bool {
    let runs = read_runs();
    let now = chrono::Utc::now();
    let elapsed_since = |r: &Value| {
        r["finished_at"]
            .as_str()
            .and_then(|s| chrono::DateTime::parse_from_rfc3339(s).ok())
            .map(|t| now.signed_duration_since(t))
    };

    if let Some(since_last) = runs.last().and_then(&elapsed_since) {
        if since_last < chrono::Duration::minutes(RETRY_DELAY_MINUTES) {
            return false;
        }
    }
    let last_success = runs.iter().rev().find(|r| r["exit_code"] == 0);
    match last_success.and_then(&elapsed_since) {
        None => true,
        Some(since_success) => since_success >= chrono::Duration::hours(interval_hours as i64),
    }
}
