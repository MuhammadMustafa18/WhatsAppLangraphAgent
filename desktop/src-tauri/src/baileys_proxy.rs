//! IPC proxy for the Baileys sidecar and the backend sidecar.
//!
//! In production Tauri builds the WebView origin is `https://tauri.localhost`.
//! Direct HTTP / WebSocket calls to `http://127.0.0.1:*` are blocked as
//! mixed-content. This module exposes Tauri commands that the Rust process
//! (which runs in a privileged context) calls on behalf of the frontend,
//! completely bypassing the mixed-content restriction.

use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tauri::{AppHandle, Emitter};

use crate::baileys_sidecar::BAILEYS_PORT;
use crate::port_check::BACKEND_PORT;

/// Shared HTTP client (connection-pooled, cheap to clone).
fn client() -> Client {
    Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
        .unwrap_or_default()
}

fn baileys_url() -> String {
    format!("http://127.0.0.1:{}", BAILEYS_PORT)
}

fn backend_url() -> String {
    format!("http://127.0.0.1:{}", BACKEND_PORT)
}

// ── Generic health proxy (used by the loading screen) ─────────────────────

/// Proxy a health-check GET to either sidecar.
/// `sidecar_id` must be "backend" or "baileys".
#[tauri::command]
pub async fn proxy_health(sidecar_id: String) -> Result<String, String> {
    let base = match sidecar_id.as_str() {
        "backend" => backend_url(),
        "baileys" => baileys_url(),
        _ => return Err(format!("unknown sidecar: {sidecar_id}")),
    };
    let url = format!("{}/health", base);
    let resp = client()
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("health check failed: {e}"))?;

    resp.text()
        .await
        .map_err(|e| format!("failed to read response: {e}"))
}

// ── Baileys-specific proxy commands ───────────────────────────────────────

/// Generic GET proxy for the baileys sidecar.
#[tauri::command]
pub async fn baileys_proxy(path: String) -> Result<String, String> {
    let url = format!("{}{}", baileys_url(), path);
    let resp = client()
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("sidecar request failed: {e}"))?;

    resp.text()
        .await
        .map_err(|e| format!("failed to read sidecar response: {e}"))
}

/// Proxy a POST with a JSON body to the baileys sidecar.
#[tauri::command]
pub async fn baileys_proxy_post(path: String, body: serde_json::Value) -> Result<String, String> {
    let url = format!("{}{}", baileys_url(), path);
    let resp = client()
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("sidecar POST failed: {e}"))?;

    resp.text()
        .await
        .map_err(|e| format!("failed to read sidecar response: {e}"))
}

// ── Typed convenience wrappers (used by the frontend) ─────────────────────

#[derive(Serialize, Deserialize, Debug)]
pub struct HealthResponse {
    pub status: String,
    pub connection: String,
    pub has_qr: bool,
}

#[tauri::command]
pub async fn baileys_health() -> Result<HealthResponse, String> {
    let raw = baileys_proxy("/health".into()).await?;
    serde_json::from_str(&raw).map_err(|e| format!("invalid health JSON: {e}"))
}

#[derive(Serialize, Deserialize, Debug)]
pub struct QrResponse {
    pub qr_image: Option<String>,
    pub qr_data: Option<String>,
}

#[tauri::command]
pub async fn baileys_get_qr() -> Result<QrResponse, String> {
    let raw = baileys_proxy("/qr".into()).await?;
    let v: serde_json::Value =
        serde_json::from_str(&raw).map_err(|e| format!("invalid QR JSON: {e}"))?;
    Ok(QrResponse {
        qr_image: v.get("qrImage").and_then(|x| x.as_str()).map(String::from),
        qr_data: v.get("qrData").and_then(|x| x.as_str()).map(String::from),
    })
}

#[derive(Serialize, Deserialize, Debug)]
pub struct StatusResponse {
    pub status: String,
    pub jid: Option<String>,
}

#[tauri::command]
pub async fn baileys_get_status() -> Result<StatusResponse, String> {
    let raw = baileys_proxy("/status".into()).await?;
    let v: serde_json::Value =
        serde_json::from_str(&raw).map_err(|e| format!("invalid status JSON: {e}"))?;
    Ok(StatusResponse {
        status: v
            .get("status")
            .and_then(|x| x.as_str())
            .unwrap_or("unknown")
            .to_string(),
        jid: v.get("jid").and_then(|x| x.as_str()).map(String::from),
    })
}

#[tauri::command]
pub async fn baileys_logout() -> Result<String, String> {
    baileys_proxy_post("/logout".into(), serde_json::json!({})).await
}

#[tauri::command]
pub async fn baileys_send_text(chat_id: String, text: String) -> Result<String, String> {
    baileys_proxy_post(
        "/send-text".into(),
        serde_json::json!({ "chatId": chat_id, "text": text }),
    )
    .await
}

// ── WebSocket event relay ─────────────────────────────────────────────────

/// Spawn a background task that connects to the sidecar's WebSocket and
/// re-emits every event through Tauri's event bus so the frontend can
/// `listen("baileys-ws-event", ...)` without opening its own WebSocket.
pub fn spawn_ws_relay(app: &AppHandle) {
    let handle = app.clone();
    let ws_url = format!("ws://127.0.0.1:{}", crate::baileys_sidecar::BAILEYS_WS_PORT);

    tauri::async_runtime::spawn(async move {
        loop {
            match tokio_tungstenite::connect_async(&ws_url).await {
                Ok((ws_stream, _)) => {
                    log::info!("[baileys-proxy] WebSocket relay connected");
                    use futures_util::StreamExt;
                    let (_, mut read) = ws_stream.split();
                    while let Some(msg) = read.next().await {
                        match msg {
                            Ok(tokio_tungstenite::tungstenite::Message::Text(text)) => {
                                let _ = handle.emit("baileys-ws-event", text.as_str());
                            }
                            Ok(tokio_tungstenite::tungstenite::Message::Close(_)) => {
                                log::warn!("[baileys-proxy] WebSocket closed by sidecar");
                                break;
                            }
                            Err(e) => {
                                log::warn!("[baileys-proxy] WebSocket error: {e}");
                                break;
                            }
                            _ => {}
                        }
                    }
                }
                Err(e) => {
                    log::debug!("[baileys-proxy] WebSocket connect failed: {e}");
                }
            }
            // Reconnect after a short delay
            tokio::time::sleep(Duration::from_secs(3)).await;
        }
    });
}
