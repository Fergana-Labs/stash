//! One-click installs for the checklist rows: the stash CLI (mirrors
//! install.sh: bootstrap uv, then `uv tool install stashai`) and the Claude
//! Code plugin (mirrors the plugin step of `stash signin`).

use std::process::Command;

fn run(desc: &str, mut cmd: Command) -> Result<(), String> {
    let out = cmd.output().map_err(|e| format!("{desc}: {e}"))?;
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        let tail: Vec<&str> = stderr.lines().rev().take(5).collect();
        let tail: Vec<&str> = tail.into_iter().rev().collect();
        return Err(format!("{desc} failed: {}", tail.join("\n")));
    }
    Ok(())
}

fn uv_present() -> bool {
    Command::new("uv")
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

#[tauri::command]
pub async fn install_cli() -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(|| {
        if !uv_present() {
            let mut bootstrap = Command::new("sh");
            bootstrap
                .arg("-c")
                .arg("curl -LsSf https://astral.sh/uv/install.sh | sh");
            run("install uv", bootstrap)?;
        }
        // Same flags as install.sh — re-run safe, upgrades an existing install.
        let mut install = Command::new("uv");
        install.args(["tool", "install", "--force", "--reinstall", "--refresh", "stashai"]);
        run("install stashai", install)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn install_plugin() -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(|| {
        // Best-effort: re-adding an existing marketplace can error, and the
        // outcome that matters is the install below (the checklist re-probes
        // the plugin registry afterwards).
        let mut add = Command::new("claude");
        add.args(["plugin", "marketplace", "add", "Fergana-Labs/stash"]);
        let _ = add.output();

        let mut install = Command::new("claude");
        install.args(["plugin", "install", "stash@stash-plugins"]);
        run("install stash plugin", install)
    })
    .await
    .map_err(|e| e.to_string())?
}
