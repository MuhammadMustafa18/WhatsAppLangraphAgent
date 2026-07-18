use std::process::{Child, Command};
use std::time::{Duration, Instant};
use std::sync::Mutex;
use tauri::{AppHandle, Manager};
use reqwest::Client;

const HEALTH_CHECK_URL: &str = "http://127.0.0.1:18234/health";
const HEALTH_CHECK_TIMEOUT: Duration = Duration::from_secs(30);
const HEALTH_CHECK_INTERVAL: Duration = Duration::from_millis(500);

/// Locate the project root when running in dev mode.
///
/// Resolution order:
///   1. `WHATSAPP_BOT_PROJECT_ROOT` env var (explicit override)
///   2. Walk up from the executable looking for `alembic.ini`
///   3. Walk up from `app_data_dir` looking for `alembic.ini`
fn resolve_project_root() -> Result<std::path::PathBuf, String> {
    if let Ok(p) = std::env::var("WHATSAPP_BOT_PROJECT_ROOT") {
        let path = std::path::PathBuf::from(p);
        if path.join("alembic.ini").exists() {
            return Ok(path);
        }
        return Err(format!(
            "WHATSAPP_BOT_PROJECT_ROOT={:?} has no alembic.ini",
            path
        ));
    }

    let exe_ancestor = std::env::current_exe()
        .ok()
        .and_then(|p| p.ancestors().nth(8).map(|a| a.to_path_buf()))
        .unwrap_or_default();

    let candidates: [std::path::PathBuf; 2] = [
        exe_ancestor,
        // Also walk up from the current working directory as a fallback.
        std::env::current_dir().ok().unwrap_or_default(),
    ];

    for start in candidates.iter().filter(|p| !p.as_os_str().is_empty()) {
        for ancestor in start.ancestors() {
            if ancestor.join("alembic.ini").exists() {
                return Ok(ancestor.to_path_buf());
            }
        }
    }

    Err(
        "Could not locate project root. Set WHATSAPP_BOT_PROJECT_ROOT to the \
         directory containing alembic.ini."
            .to_string(),
    )
}

pub struct SidecarManager {
    process: Mutex<Option<Child>>,
}

impl SidecarManager {
    pub fn new() -> Self {
        Self {
            process: Mutex::new(None),
        }
    }

    /// Start the FastAPI backend as a subprocess.
    pub fn start(&self, app_dir: &std::path::Path) -> Result<(), String> {
        // Escape hatch: skip sidecar entirely so you can run the backend
        // yourself in another terminal (faster iteration, easier log access).
        if std::env::var("WHATSAPP_BOT_SKIP_SIDECAR").ok().as_deref() == Some("1") {
            log::info!("WHATSAPP_BOT_SKIP_SIDECAR=1 — sidecar disabled");
            return Ok(());
        }

        let mut process = self.process.lock().map_err(|e| e.to_string())?;

        // Determine the Python executable path + working directory.
        //   dev mode:    run uvicorn from the project root so alembic.ini is
        //                found and migrations run against the dev SQLite.
        //   bundled:     run the PyInstaller binary; cwd = app_data_dir.
        let (cmd, args, cwd) = if cfg!(debug_assertions) {
            let project_root = resolve_project_root()?;
            let python_exe = project_root
                .join(".venv")
                .join(if cfg!(windows) { "Scripts" } else { "bin" })
                .join(if cfg!(windows) { "python.exe" } else { "python" });
            if !python_exe.exists() {
                return Err(format!("Python not found at {:?}", python_exe));
            }
            (
                python_exe.to_str().unwrap().to_string(),
                vec![
                    "-m".to_string(),
                    "uvicorn".to_string(),
                    "app.main:app".to_string(),
                    "--host".to_string(),
                    "127.0.0.1".to_string(),
                    "--port".to_string(),
                    "18234".to_string(),
                ],
                project_root,
            )
        } else {
            let exe_dir = app_dir.join("sidecars").join("python");
            let api_exe = exe_dir.join(if cfg!(windows) {
                "whatsapp-bot-api.exe"
            } else {
                "whatsapp-bot-api"
            });
            if !api_exe.exists() {
                return Err(format!("API binary not found at {:?}", api_exe));
            }
            (
                api_exe.to_str().unwrap().to_string(),
                vec!["--port".to_string(), "18234".to_string()],
                app_dir.to_path_buf(),
            )
        };

        log::info!("Starting backend: {} {:?} (cwd={:?})", cmd, args, cwd);

        let mut child = Command::new(&cmd)
            .args(&args)
            .current_dir(&cwd)
            .env("APP_DATA_DIR", app_dir.to_str().unwrap_or("./data"))
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .map_err(|e| format!("Failed to start backend: {}", e))?;

        // Drain stdout/stderr in background threads so the child never blocks
        // on a full pipe (uvicorn will hang if it can't write logs).
        if let Some(stdout) = child.stdout.take() {
            let _ = std::thread::spawn(move || {
                use std::io::{BufRead, BufReader};
                let reader = BufReader::new(stdout);
                for line in reader.lines().map_while(Result::ok) {
                    log::info!("[backend] {}", line);
                }
            });
        }
        if let Some(stderr) = child.stderr.take() {
            let _ = std::thread::spawn(move || {
                use std::io::{BufRead, BufReader};
                let reader = BufReader::new(stderr);
                for line in reader.lines().map_while(Result::ok) {
                    log::warn!("[backend] {}", line);
                }
            });
        }

        *process = Some(child);
        Ok(())
    }

    /// Wait for the backend to be ready by polling the health endpoint.
    pub async fn wait_for_ready(&self) -> Result<(), String> {
        let client = Client::new();
        let start = Instant::now();

        loop {
            if start.elapsed() > HEALTH_CHECK_TIMEOUT {
                return Err("Backend failed to start within timeout".to_string());
            }

            match client.get(HEALTH_CHECK_URL).timeout(Duration::from_secs(2)).send().await {
                Ok(resp) if resp.status().is_success() => {
                    log::info!("Backend is ready");
                    return Ok(());
                }
                Ok(resp) => {
                    log::warn!("Health check returned status: {}", resp.status());
                }
                Err(e) => {
                    log::debug!("Health check failed (expected during startup): {}", e);
                }
            }

            tokio::time::sleep(HEALTH_CHECK_INTERVAL).await;
        }
    }

    /// Stop the backend process gracefully.
    pub fn stop(&self) -> Result<(), String> {
        let mut process = self.process.lock().map_err(|e| e.to_string())?;

        if let Some(ref mut child) = *process {
            log::info!("Stopping backend process (pid={})", child.id());

            // Kill the process (graceful shutdown not supported without process group)
            let _ = child.kill();

            // Wait up to 5 seconds for graceful shutdown
            let start = Instant::now();
            while start.elapsed() < Duration::from_secs(5) {
                match child.try_wait() {
                    Ok(Some(_)) => {
                        log::info!("Backend stopped gracefully");
                        *process = None;
                        return Ok(());
                    }
                    Ok(None) => {
                        std::thread::sleep(Duration::from_millis(100));
                    }
                    Err(e) => {
                        log::error!("Error checking process status: {}", e);
                        break;
                    }
                }
            }

            // Force kill if still running
            let _ = child.kill();
            log::info!("Backend force killed");
            *process = None;
        }

        Ok(())
    }

    /// Check if the backend process is still running.
    pub fn is_running(&self) -> bool {
        if let Ok(mut process) = self.process.lock() {
            if let Some(ref mut child) = *process {
                return child.try_wait().ok().flatten().is_none();
            }
        }
        false
    }
}

/// Setup the sidecar: start backend, wait for ready, register cleanup on exit.
pub fn setup_sidecar(app: &AppHandle) -> Result<(), String> {
    log::info!("setup_sidecar: starting");
    let manager = SidecarManager::new();

    // Get the app data directory (the per-user app folder, e.g.
    // %APPDATA%\com.whatsapp-bot.app on Windows). Inside that we keep
    // runtime data in a 'data' subdir so the app folder can also hold
    // future config files, logs, etc. without collision.
    let app_dir = app.path().app_data_dir().map_err(|e| {
        log::error!("setup_sidecar: failed to get app_data_dir: {}", e);
        e.to_string()
    })?;
    let data_dir = app_dir.join("data");
    log::info!("setup_sidecar: app_data_dir = {:?}, data_dir = {:?}", app_dir, data_dir);
    std::fs::create_dir_all(&data_dir).map_err(|e| {
        log::error!("setup_sidecar: failed to create data_dir: {}", e);
        e.to_string()
    })?;

    // Start the backend
    manager.start(&data_dir)?;

    // Store manager in app state for access in other parts of the app
    app.manage(manager);

    Ok(())
}

/// Cleanup: stop the backend when the app exits.
pub fn cleanup_sidecar(app: &AppHandle) {
    if let Some(manager) = app.try_state::<SidecarManager>() {
        if let Err(e) = manager.stop() {
            log::error!("Failed to stop backend: {}", e);
        }
    }
}
