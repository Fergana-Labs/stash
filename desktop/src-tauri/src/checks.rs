//! Local onboarding checks: is the user signed in, are the stash + claude
//! CLIs on PATH, and is the Stash Claude Code plugin installed.

use serde::Serialize;

#[derive(Serialize)]
pub struct Checks {
    pub signed_in: bool,
    pub username: Option<String>,
    pub base_url: String,
    pub cli_installed: bool,
    pub cli_version: Option<String>,
    pub claude_installed: bool,
    pub plugin_installed: bool,
}

#[tauri::command]
pub async fn run_checks() -> Result<Checks, String> {
    let cfg = crate::config::load()?;
    let cli_version = command_stdout("stash", &["--version"]);
    Ok(Checks {
        signed_in: cfg.api_key.is_some(),
        username: cfg.username,
        base_url: cfg.base_url,
        cli_installed: cli_version.is_some(),
        cli_version,
        claude_installed: command_stdout("claude", &["--version"]).is_some(),
        plugin_installed: claude_plugin_installed(),
    })
}

fn command_stdout(binary: &str, args: &[&str]) -> Option<String> {
    let out = std::process::Command::new(binary).args(args).output().ok()?;
    if !out.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

/// Same probe the CLI uses (`_plugin_installed("claude")`): the plugin registry
/// at ~/.claude/plugins/installed_plugins.json has a "stash@stash-plugins" key.
fn claude_plugin_installed() -> bool {
    let path = dirs::home_dir()
        .expect("no home directory")
        .join(".claude/plugins/installed_plugins.json");
    let Ok(raw) = std::fs::read_to_string(path) else {
        return false;
    };
    let Ok(v) = serde_json::from_str::<serde_json::Value>(&raw) else {
        return false;
    };
    v["plugins"].get("stash@stash-plugins").is_some()
}
