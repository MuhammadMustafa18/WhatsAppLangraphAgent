mod ngrok;
mod port_check;
mod sidecar;

use port_check::BACKEND_PORT;
use tauri::{Listener, Manager};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Default to info so we see sidecar + backend chatter in the dev terminal.
    // Override with RUST_LOG=debug for verbose tracing.
    if std::env::var("RUST_LOG").is_err() {
        std::env::set_var("RUST_LOG", "info");
    }
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // ── Startup: kill stale processes & show service status ──
            log::info!("=== Tauri Startup ===");
            log::info!("Checking for stale processes on critical ports...");
            port_check::kill_all_stale();
            log::info!("Pre-flight port check complete.");

            // ── Spawn uvicorn (the FastAPI backend) ──
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = sidecar::setup_sidecar(&handle) {
                    log::error!("Failed to start backend sidecar: {}", e);
                    return;
                }
                log::info!("Sidecar started, waiting for backend...");
                let manager = match handle.try_state::<sidecar::SidecarManager>() {
                    Some(m) => m,
                    None => {
                        log::error!("SidecarManager not registered");
                        return;
                    }
                };
                if let Err(e) = manager.wait_for_ready().await {
                    log::error!("Backend failed to start: {}", e);
                    return;
                }
                log::info!("Backend is ready!");

                // ── Spawn ngrok pointing at the backend ──
                if let Err(e) = ngrok::setup_ngrok(&handle, BACKEND_PORT) {
                    log::warn!("Failed to spawn ngrok: {}", e);
                    log::warn!("Backend is running on 127.0.0.1:{} but has no public URL.",
                               BACKEND_PORT);
                    log::warn!("Run ngrok manually: ngrok http {}", BACKEND_PORT);
                } else {
                    let ngrok_mgr = handle
                        .try_state::<ngrok::NgrokManager>()
                        .expect("ngrok manager missing");
                    match ngrok_mgr.wait_for_ready(BACKEND_PORT).await {
                        Ok(url) => {
                            log::info!("Public URL: {}", url);
                            log::info!("Paste this into OpenWA webhook config: http://localhost:2785");
                        }
                        Err(e) => {
                            log::error!("ngrok didn't report a public URL: {}", e);
                        }
                    }
                }

                // ── Final service status report ──
                port_check::log_service_status();
                log::info!("=== Startup Complete ===");
            });

            // Cleanup on exit
            let handle = app.handle().clone();
            app.listen("exit-requested", move |_| {
                ngrok::cleanup_ngrok(&handle);
                sidecar::cleanup_sidecar(&handle);
            });

            #[cfg(debug_assertions)]
            {
                let window = app.get_webview_window("main").unwrap();
                window.open_devtools();
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                ngrok::cleanup_ngrok(window.app_handle());
                sidecar::cleanup_sidecar(window.app_handle());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}