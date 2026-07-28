//! Browser device-auth flow — the same one `stash signin` uses:
//! create a cli-auth session, open the approval page, poll until complete,
//! then persist the minted key into ~/.stash/config.json.

use crate::config;
use serde_json::{json, Value};

#[tauri::command]
pub async fn signin_start() -> Result<Value, String> {
    let base = config::load()?.base_url;
    let device = format!(
        "{} (Stash Desktop)",
        gethostname::gethostname().to_string_lossy()
    );
    let resp = reqwest::Client::new()
        .post(format!("{base}/api/v1/users/cli-auth/sessions"))
        .json(&json!({ "device_name": device }))
        .send()
        .await
        .map_err(|e| format!("create auth session: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("create auth session: HTTP {}", resp.status().as_u16()));
    }
    let body: Value = resp.json().await.map_err(|e| e.to_string())?;
    let session_id = body["session_id"]
        .as_str()
        .ok_or("auth session response missing session_id")?
        .to_string();
    let url = signin_page(&base, &session_id);
    tauri_plugin_opener::open_url(&url, None::<&str>).map_err(|e| e.to_string())?;
    Ok(json!({ "session_id": session_id, "url": url }))
}

/// Mirrors the CLI's API-host → web-app-host mapping (cli/main.py:130-138).
fn signin_page(base: &str, session_id: &str) -> String {
    let web = if base == config::PRODUCTION_BASE_URL {
        "https://joinstash.ai".to_string()
    } else if base.contains(":3456") {
        base.replace(":3456", ":3457")
    } else {
        base.replace("://api.", "://app.")
    };
    format!("{web}/connect-token?session={session_id}")
}

/// One poll tick. When the session completes, the key is saved before this
/// returns, so a `complete` status means the app is signed in.
#[tauri::command]
pub async fn signin_poll(session_id: String) -> Result<Value, String> {
    let base = config::load()?.base_url;
    let resp = reqwest::Client::new()
        .get(format!("{base}/api/v1/users/cli-auth/sessions/{session_id}"))
        .send()
        .await
        .map_err(|e| format!("poll auth session: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("poll auth session: HTTP {}", resp.status().as_u16()));
    }
    let body: Value = resp.json().await.map_err(|e| e.to_string())?;
    if body["status"] == "complete" {
        let api_key = body["api_key"]
            .as_str()
            .ok_or("complete auth session missing api_key")?;
        let username = body["username"].as_str().unwrap_or_default();
        config::save_keys(&[
            ("base_url", &base),
            ("api_key", api_key),
            ("username", username),
        ])?;
    }
    Ok(json!({ "status": body["status"] }))
}
