//! The "Session uploads" card: which folders stream sessions to Stash.
//!
//! Streaming is on globally once signed in; `excluded_paths` in
//! ~/.stash/config.json is the per-folder opt-out the plugin hooks enforce
//! (stashai/plugin/scope.py::cwd_in_scope). The plugins also keep a rolling
//! `recent_cwds` list in their state files, which is what makes "these
//! folders have been uploading" visible here.

use crate::config;
use serde_json::{json, Value};
use std::path::PathBuf;

fn state_files() -> Vec<(String, PathBuf)> {
    let home = dirs::home_dir().expect("no home directory");
    let mut files = vec![(
        "claude".to_string(),
        home.join(".claude/plugins/data/stash-stash-plugins/state.json"),
    )];
    let others = home.join(".stash/plugins");
    if let Ok(entries) = std::fs::read_dir(others) {
        for entry in entries.flatten() {
            let agent = entry.file_name().to_string_lossy().into_owned();
            files.push((agent, entry.path().join("state.json")));
        }
    }
    files
}

/// Folders that have streamed sessions recently, newest-ish first, deduped
/// across agents.
fn recent_dirs() -> Vec<String> {
    let mut seen = Vec::new();
    for (_agent, path) in state_files() {
        let Ok(raw) = std::fs::read_to_string(&path) else {
            continue;
        };
        let Ok(state) = serde_json::from_str::<Value>(&raw) else {
            continue;
        };
        if let Some(list) = state["recent_cwds"].as_array() {
            for c in list.iter().filter_map(Value::as_str) {
                if !c.is_empty() && !seen.iter().any(|s| s == c) {
                    seen.push(c.to_string());
                }
            }
        }
    }
    seen
}

fn excluded_paths(cfg: &Value) -> Vec<String> {
    cfg["excluded_paths"]
        .as_array()
        .map(|l| {
            l.iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

#[tauri::command]
pub fn upload_settings() -> Result<Value, String> {
    let cfg = config::raw()?;
    Ok(json!({
        "streaming": cfg["stopped_streaming"] != true,
        "excluded_paths": excluded_paths(&cfg),
        "recent_dirs": recent_dirs(),
    }))
}

#[tauri::command]
pub fn set_streaming(enabled: bool) -> Result<(), String> {
    config::save_values(&[("stopped_streaming", Value::Bool(!enabled))])
}

#[tauri::command]
pub fn exclude_path(path: String) -> Result<(), String> {
    if path.trim().is_empty() {
        return Err("empty path".into());
    }
    let cfg = config::raw()?;
    let mut paths = excluded_paths(&cfg);
    if !paths.contains(&path) {
        paths.push(path);
    }
    config::save_values(&[("excluded_paths", json!(paths))])
}

#[tauri::command]
pub fn include_path(path: String) -> Result<(), String> {
    let cfg = config::raw()?;
    let paths: Vec<String> = excluded_paths(&cfg).into_iter().filter(|p| p != &path).collect();
    config::save_values(&[("excluded_paths", json!(paths))])
}
