//! Reads and updates `~/.stash/config.json` — the same file the `stash` CLI
//! and the agent plugins use, so the desktop app shares their identity.

use serde::Serialize;
use serde_json::Value;
use std::path::PathBuf;

pub const PRODUCTION_BASE_URL: &str = "https://api.joinstash.ai";

#[derive(Debug, Clone, Serialize, Default)]
pub struct StashConfig {
    pub base_url: String,
    pub api_key: Option<String>,
    pub username: Option<String>,
    pub scope: Option<String>,
}

pub fn config_path() -> PathBuf {
    dirs::home_dir()
        .expect("no home directory")
        .join(".stash/config.json")
}

pub fn load() -> Result<StashConfig, String> {
    let path = config_path();
    if !path.exists() {
        return Ok(StashConfig {
            base_url: PRODUCTION_BASE_URL.to_string(),
            ..Default::default()
        });
    }
    let raw = std::fs::read_to_string(&path)
        .map_err(|e| format!("read {}: {e}", path.display()))?;
    let v: Value = serde_json::from_str(&raw)
        .map_err(|e| format!("parse {}: {e}", path.display()))?;
    let field = |key: &str| v.get(key).and_then(Value::as_str).map(str::to_string);
    let base_url = field("base_url")
        .filter(|u| !u.is_empty())
        .unwrap_or_else(|| PRODUCTION_BASE_URL.to_string());
    Ok(StashConfig {
        base_url: base_url.trim_end_matches('/').to_string(),
        api_key: field("api_key").filter(|k| !k.is_empty()),
        username: field("username"),
        scope: field("scope"),
    })
}

/// Merge key/value pairs into the config file, preserving every key we don't
/// own — the CLI stores its own settings (enabled_agents, scope, …) here too.
pub fn save_keys(pairs: &[(&str, &str)]) -> Result<(), String> {
    let values: Vec<(&str, Value)> = pairs
        .iter()
        .map(|(k, v)| (*k, Value::String(v.to_string())))
        .collect();
    save_values(&values)
}

/// Same merge semantics for non-string values (lists, booleans).
pub fn save_values(pairs: &[(&str, Value)]) -> Result<(), String> {
    let path = config_path();
    let mut root: Value = match std::fs::read_to_string(&path) {
        Ok(raw) => serde_json::from_str(&raw)
            .map_err(|e| format!("parse {}: {e}", path.display()))?,
        Err(_) => Value::Object(Default::default()),
    };
    let obj = root
        .as_object_mut()
        .ok_or_else(|| format!("{} is not a JSON object", path.display()))?;
    for (key, value) in pairs {
        obj.insert(key.to_string(), value.clone());
    }
    let parent = path.parent().expect("config path has a parent");
    std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let pretty = serde_json::to_string_pretty(&root).expect("serialize config");
    std::fs::write(&path, pretty + "\n").map_err(|e| format!("write {}: {e}", path.display()))
}

pub fn raw() -> Result<Value, String> {
    let path = config_path();
    if !path.exists() {
        return Ok(Value::Object(Default::default()));
    }
    let text = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| format!("parse {}: {e}", path.display()))
}
