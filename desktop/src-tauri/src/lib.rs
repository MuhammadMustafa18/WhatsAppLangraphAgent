mod sidecar;

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
            // Setup the backend sidecar
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                match sidecar::setup_sidecar(&handle) {
                    Ok(()) => {
                        log::info!("Sidecar started, waiting for backend...");
                        if let Some(manager) = handle.try_state::<sidecar::SidecarManager>() {
                            if let Err(e) = manager.wait_for_ready().await {
                                log::error!("Backend failed to start: {}", e);
                            } else {
                                log::info!("Backend is ready!");
                            }
                        }
                    }
                    Err(e) => {
                        log::error!("Failed to start sidecar: {}", e);
                    }
                }
            });

            // Cleanup on exit
            let handle = app.handle().clone();
            app.listen("exit-requested", move |_| {
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
                sidecar::cleanup_sidecar(window.app_handle());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
