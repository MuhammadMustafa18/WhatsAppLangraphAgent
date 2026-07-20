use std::process::{Child, Command};
use std::time::{Duration, Instant};
use std::sync::Mutex;
use tauri::{AppHandle, Manager};
use reqwest::Client;

/// Default port for the Baileys sidecar HTTP API.
pub const BAILEYS_PORT: u16 = 2786;

/// WebSocket port for QR / status broadcast to the React UI.
pub const BAILEYS_WS_PORT: u16 = 2787;

const HEALTH_CHECK_TIMEOUT: Duration = Duration::from_secs(30);
const HEALTH_CHECK_INTERVAL: Duration = Duration::from_millis(500);


pub struct BaileysManager {
    process: Mutex<Option<Child>>,
}

impl BaileysManager {
    pub fn new() -> Self {
        Self {
            process: Mutex::new(None),
        }
    }

    /// Resolve the baileys sidecar binary path.
    ///
    /// Resolution order:
    ///   1. `WHATSAPP_BOT_BAILEYS_BIN` env var (explicit override).
    ///   2. Side-by-side with the Python API bundle in release builds.
    ///   3. `baileys-sidecar/baileys-sidecar.ts` via `tsx` in dev mode.
    fn resolve_binary(app_dir: &std::path::Path) -> Result<(String, Vec<String>, std::path::PathBuf), String> {
        // Allow skipping entirely (for testing / CI)
        if std::env::var("WHATSAPP_BOT_SKIP_BAILEYS").ok().as_deref() == Some("1") {
            log::info!("WHATSAPP_BOT_SKIP_BAILEYS=1 — baileys sidecar disabled");
            return Err("skipped".to_string());
        }

        // Explicit override
        if let Ok(bin) = std::env::var("WHATSAPP_BOT_BAILEYS_BIN") {
            let p = std::path::PathBuf::from(&bin);
            if p.exists() {
                return Ok((bin, vec![], p.parent().unwrap_or(&p).to_path_buf()));
            }
        }

        if cfg!(debug_assertions) {
            // Dev mode: run via tsx from baileys-sidecar/
            let project_root = resolve_project_root()?;
            let sidecar_dir = project_root.join("baileys-sidecar");
            let tsx_exe = sidecar_dir
                .join("node_modules")
                .join(".bin")
                .join(if cfg!(windows) { "tsx.cmd" } else { "tsx" });

            let sidecar_ts = sidecar_dir.join("baileys-sidecar.ts");

            if !tsx_exe.exists() {
                return Err(format!(
                    "tsx not found at {:?}. Run: cd baileys-sidecar && npm install",
                    tsx_exe
                ));
            }
            if !sidecar_ts.exists() {
                return Err(format!(
                    "baileys-sidecar.ts not found at {:?}",
                    sidecar_ts
                ));
            }

            Ok((
                tsx_exe.to_string_lossy().to_string(),
                vec![sidecar_ts.to_string_lossy().to_string()],
                sidecar_dir,
            ))
        } else {
            // Release mode: bundled sidecar next to the Python API binary
            let exe_name = if cfg!(windows) {
                "baileys-sidecar.exe"
            } else {
                "baileys-sidecar"
            };
            let bin_path = app_dir.join("sidecars").join(exe_name);
            if !bin_path.exists() {
                return Err(format!(
                    "baileys-sidecar binary not found at {:?}. \
                     Run: cd baileys-sidecar && npm run build && npm run compile, \
                     then copy the output to sidecars/",
                    bin_path
                ));
            }
            Ok((
                bin_path.to_string_lossy().to_string(),
                vec![],
                app_dir.to_path_buf(),
            ))
        }
    }

    /// Start the Baileys sidecar process.
    pub fn start(&self, app_dir: &std::path::Path) -> Result<(), String> {
        let mut process = self.process.lock().map_err(|e| e.to_string())?;
        if process.is_some() {
            return Err("Baileys sidecar already running".to_string());
        }

        // Ensure our ports are free before spawning
        crate::port_check::ensure_port_free(BAILEYS_PORT)?;
        crate::port_check::ensure_port_free(BAILEYS_WS_PORT)?;

        let (cmd, args, cwd) = Self::resolve_binary(app_dir)?;

        log::info!(
            "Starting baileys sidecar: command={}, args={:?}, cwd={:?}",
            cmd, args, cwd
        );

        let mut child = Command::new(&cmd)
            .args(&args)
            .current_dir(&cwd)
            .env("BAILEYS_PORT", BAILEYS_PORT.to_string())
            .env("APP_DATA_DIR", app_dir.to_str().unwrap_or("./data"))
            .env("BACKEND_URL", "http://127.0.0.1:18234")
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .map_err(|e| format!("Failed to start baileys sidecar: {}", e))?;

        log::info!("Baileys sidecar started: pid={}", child.id());

        // Drain stdout/stderr in background threads
        if let Some(stdout) = child.stdout.take() {
            let _ = std::thread::spawn(move || {
                use std::io::{BufRead, BufReader};
                let reader = BufReader::new(stdout);
                for line in reader.lines().map_while(Result::ok) {
                    log::info!("[baileys] {}", line);
                }
                log::info!("[baileys] stdout closed");
            });
        }
        if let Some(stderr) = child.stderr.take() {
            let _ = std::thread::spawn(move || {
                use std::io::{BufRead, BufReader};
                let reader = BufReader::new(stderr);
                for line in reader.lines().map_while(Result::ok) {
                    log::warn!("[baileys] {}", line);
                }
                log::info!("[baileys] stderr closed");
            });
        }

        *process = Some(child);
        Ok(())
    }

    /// Wait for the sidecar's /health endpoint to respond OK.
    pub async fn wait_for_ready(&self) -> Result<(), String> {
        let health_url = format!("http://127.0.0.1:{}/health", BAILEYS_PORT);
        let client = Client::new();
        let start = Instant::now();

        loop {
            if start.elapsed() > HEALTH_CHECK_TIMEOUT {
                return Err("Baileys sidecar failed to start within timeout".to_string());
            }

            match client
                .get(&health_url)
                .timeout(Duration::from_secs(2))
                .send()
                .await
            {
                Ok(resp) if resp.status().is_success() => {
                    log::info!("Baileys sidecar is ready");
                    return Ok(());
                }
                Ok(resp) => {
                    log::warn!("Baileys health check returned status: {}", resp.status());
                }
                Err(e) => {
                    log::debug!("Baileys health check failed (expected during startup): {}", e);
                }
            }

            tokio::time::sleep(HEALTH_CHECK_INTERVAL).await;
        }
    }

    /// Stop the Baileys sidecar process.
    pub fn stop(&self) -> Result<(), String> {
        let mut process = self.process.lock().map_err(|e| e.to_string())?;

        if let Some(ref mut child) = *process {
            log::info!("Stopping baileys sidecar: pid={}", child.id());

            let _ = child.kill();

            let start = Instant::now();
            while start.elapsed() < Duration::from_secs(5) {
                match child.try_wait() {
                    Ok(Some(status)) => {
                        log::info!(
                            "Baileys sidecar stopped: pid={}, exit_code={}",
                            child.id(),
                            status.code().unwrap_or(-1)
                        );
                        *process = None;
                        return Ok(());
                    }
                    Ok(None) => {
                        std::thread::sleep(Duration::from_millis(100));
                    }
                    Err(e) => {
                        log::error!("Error checking baileys status: {}", e);
                        break;
                    }
                }
            }

            let _ = child.kill();
            log::warn!("Baileys sidecar force killed after timeout: pid={}", child.id());
            *process = None;
        }

        Ok(())
    }

}


/// Locate the project root when running in dev mode.
fn resolve_project_root() -> Result<std::path::PathBuf, String> {
    if let Ok(p) = std::env::var("WHATSAPP_BOT_PROJECT_ROOT") {
        let path = std::path::PathBuf::from(p);
        if path.join("baileys-sidecar").join("baileys-sidecar.ts").exists() {
            return Ok(path);
        }
        return Err(format!(
            "WHATSAPP_BOT_PROJECT_ROOT={:?} has no baileys-sidecar directory",
            path
        ));
    }

    let exe_ancestor = std::env::current_exe()
        .ok()
        .and_then(|p| p.ancestors().nth(8).map(|a| a.to_path_buf()))
        .unwrap_or_default();

    let candidates: [std::path::PathBuf; 2] = [
        exe_ancestor,
        std::env::current_dir().ok().unwrap_or_default(),
    ];

    for start in candidates.iter().filter(|p| !p.as_os_str().is_empty()) {
        for ancestor in start.ancestors() {
            if ancestor.join("baileys-sidecar").join("baileys-sidecar.ts").exists() {
                return Ok(ancestor.to_path_buf());
            }
        }
    }

    Err(
        "Could not locate project root (looked for baileys-sidecar/ directory). \
         Set WHATSAPP_BOT_PROJECT_ROOT to the repo root."
            .to_string(),
    )
}


/// Tauri setup hook: spawn the Baileys sidecar, store the manager in app state.
pub fn setup_baileys(app: &AppHandle) -> Result<(), String> {
    log::info!("Setting up Baileys sidecar");

    let app_dir = app.path().app_data_dir().map_err(|e| {
        log::error!("Failed to get app_data_dir: {}", e);
        e.to_string()
    })?;
    let data_dir = app_dir.join("data");
    std::fs::create_dir_all(&data_dir).map_err(|e| {
        log::error!("Failed to create data_dir: {}", e);
        e.to_string()
    })?;

    let manager = BaileysManager::new();
    manager.start(&data_dir)?;
    app.manage(manager);
    Ok(())
}

/// Tauri cleanup hook: stop the Baileys sidecar on exit.
pub fn cleanup_baileys(app: &AppHandle) {
    if let Some(manager) = app.try_state::<BaileysManager>() {
        if let Err(e) = manager.stop() {
            log::error!("Failed to stop baileys sidecar: {}", e);
        }
    }
}
