mod baileys_proxy;
mod baileys_sidecar;
mod port_check;
mod sidecar;

use tauri::{Emitter, Listener, Manager};

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
        .invoke_handler(tauri::generate_handler![
            baileys_proxy::proxy_health,
            baileys_proxy::baileys_proxy,
            baileys_proxy::baileys_proxy_post,
            baileys_proxy::baileys_health,
            baileys_proxy::baileys_get_qr,
            baileys_proxy::baileys_get_status,
            baileys_proxy::baileys_logout,
            baileys_proxy::baileys_send_text,
        ])
        .setup(|app| {
            // ── Startup: kill stale processes & show service status ──
            log::info!("=== Tauri Startup ===");
            log::info!("Checking for stale processes on critical ports...");
            port_check::kill_all_stale();
            log::info!("Pre-flight port check complete.");

            // ── Spawn uvicorn (the FastAPI backend) ──
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                // Helper to emit sidecar errors to the WebView so the loading
                // screen can show the specific failure reason.
                let emit_error = |id: &str, msg: &str| {
                    let _ = handle.emit(
                        "sidecar-error",
                        serde_json::json!({"id": id, "error": msg}),
                    );
                };

                if let Err(e) = sidecar::setup_sidecar(&handle) {
                    log::error!("Failed to start backend sidecar: {}", e);
                    emit_error("backend", &e);
                    return;
                }
                log::info!("Sidecar started, waiting for backend...");
                let uvicorn = match handle.try_state::<sidecar::SidecarManager>() {
                    Some(m) => m,
                    None => {
                        let msg = "SidecarManager not registered";
                        log::error!("{}", msg);
                        emit_error("backend", msg);
                        return;
                    }
                };
                if let Err(e) = uvicorn.wait_for_ready().await {
                    log::error!("Backend failed to start: {}", e);
                    emit_error("backend", &e);
                    return;
                }
                log::info!("Backend is ready!");

                // ── Spawn the Baileys WhatsApp gateway sidecar ──
                if let Err(e) = baileys_sidecar::setup_baileys(&handle) {
                    log::warn!("Failed to start Baileys sidecar: {}", e);
                    emit_error("baileys", &e);
                    log::warn!("WhatsApp gateway unavailable. No ngrok/OpenWA needed.");
                } else {
                    let baileys = handle
                        .try_state::<baileys_sidecar::BaileysManager>()
                        .expect("BaileysManager not registered");
                    if let Err(e) = baileys.wait_for_ready().await {
                        log::error!("Baileys sidecar didn't come online: {}", e);
                        emit_error("baileys", &e);
                    } else {
                        // Start WebSocket event relay so the frontend can receive
                        // QR / status updates via Tauri events instead of direct WS.
                        baileys_proxy::spawn_ws_relay(&handle);
                    }
                }

                // ── Final service status report ──
                port_check::log_service_status();
                log::info!("=== Startup Complete ===");
            });

            // Cleanup on exit
            let handle = app.handle().clone();
            app.listen("exit-requested", move |_| {
                baileys_sidecar::cleanup_baileys(&handle);
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
                baileys_sidecar::cleanup_baileys(window.app_handle());
                sidecar::cleanup_sidecar(window.app_handle());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
