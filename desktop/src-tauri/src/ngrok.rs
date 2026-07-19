//! ngrok tunnel orchestration.
//!
//! Phase 1: spawn ngrok, wait for it to print a public URL via its local
//! inspector at :4040, return the URL so the user can copy it into
//! OpenWA's webhook config (we don't auto-POST to OpenWA yet —
//! deferred until the rest of the UX is settled).
//!
//! ngrok binary resolution:
//!   1. WHATSAPP_BOT_NGROK_BIN env var (explicit override).
//!   2. PATH search for `ngrok` / `ngrok.exe`.
//!
//! Auth token: read from `NGROK_AUTHTOKEN` (same var the backend uses),
//! registered with ngrok via `ngrok config add-authtoken` before the
//! tunnel starts. Idempotent — re-running just confirms.

use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::Manager;
use serde::Deserialize;

const NGROK_INSPECTOR_URL: &str = "http://127.0.0.1:4040/api/tunnels";
const NGROK_STARTUP_TIMEOUT: Duration = Duration::from_secs(30);
const NGROK_POLL_INTERVAL: Duration = Duration::from_millis(500);


/// One row from the ngrok inspector API. We only deserialize the fields
/// we actually use; the inspector returns more keys we don't care about.
#[derive(Debug, Deserialize)]
struct NgrokTunnel {
    public_url: String,
    proto: String,
    config: NgrokTunnelConfig,
}

#[derive(Debug, Deserialize)]
struct NgrokTunnelConfig {
    addr: String,
}


/// Owns the ngrok child process so we can kill it cleanly on app exit.
pub struct NgrokManager {
    process: Mutex<Option<Child>>,
    /// The URL ngrok assigned us. Set after `wait_for_ready` succeeds.
    /// Surfaced to the rest of the app via Tauri state.
    public_url: Mutex<Option<String>>,
}

impl NgrokManager {
    pub fn new() -> Self {
        Self {
            process: Mutex::new(None),
            public_url: Mutex::new(None),
        }
    }

    pub fn public_url(&self) -> Option<String> {
        self.public_url.lock().ok().and_then(|g| g.clone())
    }

    pub fn is_running(&self) -> bool {
        if let Ok(mut process) = self.process.lock() {
            if let Some(ref mut child) = *process {
                return child.try_wait().ok().flatten().is_none();
            }
        }
        false
    }

    /// Spawn the ngrok binary as a subprocess.
    ///
    /// ngrok binary resolution:
    ///   1. Look for `WHATSAPP_BOT_NGROK_BIN` env var (explicit override).
    ///   2. Walk PATH looking for `ngrok` / `ngrok.exe`.
    ///   3. Error with a clear message — no silent fallback.
    ///
    /// The authtoken is read from `NGROK_AUTHTOKEN` (same var the
    /// backend uses — already in the user's `.env`). We use it as the
    /// `Ngrok-Header-Var` only for path auth OR pass it via
    /// `--authtoken` (which writes to ngrok's config file for this
    /// process's lifetime, but doesn't persist after ngrok exits).
    /// We pick the `ngrok config add-authtoken` approach as a one-shot
    /// before starting the tunnel — it sets the token in the ngrok
    /// config file for this user so the tunnel command is clean.
    pub fn start(&self, port: u16) -> Result<(), String> {
        // Allow skipping for local-only development (no public URL needed
        // when the user is testing via curl). Mirrors the backend's
        // WHATSAPP_BOT_SKIP_SIDECAR pattern.
        if std::env::var("WHATSAPP_BOT_SKIP_NGROK").ok().as_deref() == Some("1") {
            log::info!("WHATSAPP_BOT_SKIP_NGROK=1 — tunnel disabled");
            return Ok(());
        }

        let mut process = self.process.lock().map_err(|e| e.to_string())?;
        if process.is_some() {
            return Err("ngrok already running".to_string());
        }

        let bin = resolve_ngrok_binary()?;

        // Ensure ngrok's inspector port (4040) is free
        crate::port_check::ensure_port_free(4040)?;

        // If NGROK_AUTHTOKEN is set in env, register it with ngrok first
        // (writes to the user's config file). This is idempotent — if
        // the token is already registered, ngrok just confirms.
        if let Ok(token) = std::env::var("NGROK_AUTHTOKEN") {
            if !token.is_empty() {
                log::info!("Registering NGROK_AUTHTOKEN with ngrok...");
                let status = Command::new(&bin)
                    .args(["config", "add-authtoken", &token])
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .status()
                    .map_err(|e| format!("Failed to register ngrok token: {}", e))?;
                if !status.success() {
                    log::warn!(
                        "ngrok config add-authtoken exited with {:?}; \
                         continuing anyway (token may already be registered)",
                        status.code()
                    );
                }
            }
        }

        let args = vec!["http".to_string(), port.to_string()];

        log::info!(
            "Starting ngrok tunnel: binary={}, args={:?}, target_port={}",
            bin, args, port
        );

        let mut child = Command::new(&bin)
            .args(&args)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .map_err(|e| format!("Failed to start ngrok at {:?}: {}", bin, e))?;

        log::info!(
            "ngrok process started: pid={}, port=4040",
            child.id()
        );

        // Drain output so the pipes don't fill up.
        if let Some(stdout) = child.stdout.take() {
            let _ = std::thread::spawn(move || {
                use std::io::{BufRead, BufReader};
                let reader = BufReader::new(stdout);
                for line in reader.lines().map_while(Result::ok) {
                    log::info!("[ngrok] {}", line);
                }
            });
        }
        if let Some(stderr) = child.stderr.take() {
            let _ = std::thread::spawn(move || {
                use std::io::{BufRead, BufReader};
                let reader = BufReader::new(stderr);
                for line in reader.lines().map_while(Result::ok) {
                    log::warn!("[ngrok] {}", line);
                }
            });
        }

        *process = Some(child);
        Ok(())
    }

    /// Poll the ngrok inspector until it reports our tunnel, then return
    /// the public URL. Times out after NGROK_STARTUP_TIMEOUT.
    pub async fn wait_for_ready(&self, port: u16) -> Result<String, String> {
        let client = reqwest::Client::new();
        let start = Instant::now();
        let target_addr = format!("http://localhost:{}", port);

        loop {
            if start.elapsed() > NGROK_STARTUP_TIMEOUT {
                return Err(format!(
                    "ngrok didn't report a public URL within {:?}",
                    NGROK_STARTUP_TIMEOUT
                ));
            }

            // ngrok's inspector returns 502 before it's fully ready; treat
            // any parseable response as a candidate. Filter by addr match
            // in case there are stale tunnels from prior runs.
            if let Ok(resp) = client.get(NGROK_INSPECTOR_URL).send().await {
                if resp.status().is_success() {
                    if let Ok(body) = resp.json::<serde_json::Value>().await {
                        if let Some(url) = extract_url_for(&body, &target_addr) {
                            log::info!("ngrok tunnel ready: {}", url);
                            if let Ok(mut guard) = self.public_url.lock() {
                                *guard = Some(url.clone());
                            }
                            return Ok(url);
                        }
                    }
                }
            }

            tokio::time::sleep(NGROK_POLL_INTERVAL).await;
        }
    }

    /// Kill the ngrok child. Idempotent.
    pub fn stop(&self) -> Result<(), String> {
        let mut process = self.process.lock().map_err(|e| e.to_string())?;
        if let Some(ref mut child) = *process {
            log::info!(
                "Stopping ngrok: pid={}, port=4040",
                child.id()
            );
            let _ = child.kill();
            *process = None;
        }
        Ok(())
    }
}


/// Find the ngrok binary. Explicit override first, then PATH search.
fn resolve_ngrok_binary() -> Result<String, String> {
    if let Ok(p) = std::env::var("WHATSAPP_BOT_NGROK_BIN") {
        if !p.is_empty() && std::path::Path::new(&p).exists() {
            return Ok(p);
        }
    }

    // Walk PATH looking for the executable.
    let exe_name = if cfg!(windows) { "ngrok.exe" } else { "ngrok" };
    if let Ok(path_var) = std::env::var("PATH") {
        for dir in std::env::split_paths(&path_var) {
            let candidate = dir.join(exe_name);
            if candidate.is_file() {
                return Ok(candidate.to_string_lossy().into_owned());
            }
        }
    }

    Err(format!(
        "ngrok binary not found. Install it (https://ngrok.com/download) \
         and ensure `{}` is on PATH, or set WHATSAPP_BOT_NGROK_BIN.",
        exe_name
    ))
}


/// Inspect the ngrok API response and return the public_url whose
/// `config.addr` matches our target (e.g. http://localhost:18234).
fn extract_url_for(body: &serde_json::Value, target_addr: &str) -> Option<String> {
    let tunnels = body.get("tunnels")?.as_array()?;
    for tunnel in tunnels {
        let public_url = tunnel.get("public_url")?.as_str()?.to_string();
        let proto = tunnel.get("proto")?.as_str()?;
        let addr = tunnel.get("config")?.get("addr")?.as_str()?;
        // We want the HTTPS tunnel pointing at our backend port.
        if proto == "https" && addr == target_addr {
            return Some(public_url);
        }
    }
    None
}


/// Tauri setup hook: spawn ngrok, store the manager in app state so
/// the UI can read `public_url` later.
pub fn setup_ngrok(app: &tauri::AppHandle, backend_port: u16) -> Result<(), String> {
    log::info!("Setting up ngrok tunnel");
    let manager = NgrokManager::new();
    manager.start(backend_port)?;
    app.manage(manager);
    Ok(())
}

/// Tauri cleanup hook: stop ngrok alongside uvicorn.
pub fn cleanup_ngrok(app: &tauri::AppHandle) {
    if let Some(manager) = app.try_state::<NgrokManager>() {
        if let Err(e) = manager.stop() {
            log::error!("Failed to stop ngrok: {}", e);
        }
    }
}
