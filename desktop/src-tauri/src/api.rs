//! Thin async client for the Stash backend. All HTTP happens here in Rust so
//! the API key never enters the webview.

use crate::config;
use serde_json::Value;
use std::time::Duration;

struct Session {
    base: String,
    key: String,
    scope: Option<String>,
}

fn http() -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .expect("build http client")
}

fn session() -> Result<Session, String> {
    let cfg = config::load()?;
    let key = cfg.api_key.ok_or("Not signed in")?;
    Ok(Session {
        base: cfg.base_url,
        key,
        scope: cfg.scope,
    })
}

async fn parse(resp: reqwest::Response, path: &str) -> Result<Value, String> {
    let status = resp.status();
    let body: Value = resp
        .json()
        .await
        .map_err(|e| format!("{path}: bad response body: {e}"))?;
    if !status.is_success() {
        let detail = body["detail"].as_str().unwrap_or("").to_string();
        return Err(format!("{} {path}: {detail}", status.as_u16()));
    }
    Ok(body)
}

async fn get(path: &str) -> Result<Value, String> {
    let s = session()?;
    let mut req = http()
        .get(format!("{}{path}", s.base))
        .bearer_auth(&s.key);
    if let Some(scope) = &s.scope {
        req = req.header("X-Stash-Scope", scope);
    }
    let resp = req.send().await.map_err(|e| format!("{path}: {e}"))?;
    parse(resp, path).await
}

#[tauri::command]
pub async fn backend_health() -> Result<bool, String> {
    let base = config::load()?.base_url;
    let resp = http()
        .get(format!("{base}/health"))
        .send()
        .await
        .map_err(|e| e.to_string())?;
    Ok(resp.status().is_success())
}

#[tauri::command]
pub async fn whoami() -> Result<Value, String> {
    get("/api/v1/users/me").await
}

#[tauri::command]
pub async fn list_integrations() -> Result<Value, String> {
    get("/api/v1/integrations").await
}

#[tauri::command]
pub async fn list_sources() -> Result<Value, String> {
    get("/api/v1/me/sources").await
}

/// The server-side Memory curator's row from `/me/agents` (is_curator = true),
/// or null when the account has none.
#[tauri::command]
pub async fn curator_status() -> Result<Value, String> {
    let body = get("/api/v1/me/agents").await?;
    let agents = body["agents"]
        .as_array()
        .ok_or("agents list missing from response")?;
    let curator = agents
        .iter()
        .find(|a| a["is_curator"] == true)
        .cloned()
        .unwrap_or(Value::Null);
    Ok(curator)
}

/// Kick the server-side Memory curator now instead of waiting for the nightly
/// tick. 409 (nothing new) and 402 (out of credits) come back as errors with
/// the backend's own message.
#[tauri::command]
pub async fn recompute_memory() -> Result<Value, String> {
    let s = session()?;
    let path = "/api/v1/me/memory/recompute";
    let mut req = http()
        .post(format!("{}{path}", s.base))
        .bearer_auth(&s.key);
    if let Some(scope) = &s.scope {
        req = req.header("X-Stash-Scope", scope);
    }
    let resp = req.send().await.map_err(|e| format!("{path}: {e}"))?;
    parse(resp, path).await
}
