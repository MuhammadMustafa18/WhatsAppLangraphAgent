//! Port management and service status observability.
//!
//! On startup, checks all critical ports and reports their status.
//! Kills stale processes on **Tauri-managed** ports before spawning
//! fresh ones.
//!
//! Managed ports:
//!   18234  — uvicorn (Python FastAPI backend)
//!   2786   — Baileys sidecar (WhatsApp gateway)
//!   2787   — Baileys sidecar WebSocket (QR / status for React UI)

use std::process::Command;

// ── Port constants: single source of truth ──────────────────────────────

/// Backend FastAPI / uvicorn port.
pub const BACKEND_PORT: u16 = 18234;

/// Baileys sidecar HTTP API (replaces OpenWA + ngrok).
pub const BAILEYS_PORT: u16 = 2786;

/// Baileys sidecar WebSocket (QR codes / connection status for React UI).
pub const BAILEYS_WS_PORT: u16 = 2787;

/// Ports Tauri manages: kills stale processes before starting fresh ones.
const MANAGED_PORTS: [u16; 3] = [BACKEND_PORT, BAILEYS_PORT, BAILEYS_WS_PORT];

/// All ports we know about (for observability / status reporting).
const KNOWN_PORTS: [u16; 4] = [
    BACKEND_PORT,
    BAILEYS_PORT,
    BAILEYS_WS_PORT,
    2785, // OpenWA — only if the user still runs Docker
];


/// Status of a single service port.
#[derive(Debug, Clone)]
pub struct PortStatus {
    pub name: String,
    pub port: u16,
    pub in_use: bool,
    pub pid: Option<u32>,
    pub process_name: Option<String>,
}

/// Check if a port is in use and return the owning PID.
/// Uses `netstat -ano` on Windows, `lsof -ti :PORT` on Unix.
pub fn check_port(port: u16) -> PortStatus {
    let (in_use, pid, process_name) = if cfg!(windows) {
        check_port_windows(port)
    } else {
        check_port_unix(port)
    };

    PortStatus {
        name: service_name_for(port),
        port,
        in_use,
        pid,
        process_name,
    }
}

/// Check all known ports and return their statuses.
/// This includes user-managed ports (OpenWA) for observability.
pub fn check_all_ports() -> Vec<PortStatus> {
    KNOWN_PORTS
        .iter()
        .map(|port| check_port(*port))
        .collect()
}

/// Log all port statuses as structured JSON.
pub fn log_service_status() {
    let statuses = check_all_ports();

    log::info!("=== Service Status ===");
    for status in &statuses {
        if status.in_use {
            log::info!(
                "Port check: service={}, port={}, status=running, pid={}, process={}",
                status.name,
                status.port,
                status.pid.unwrap_or(0),
                status.process_name.as_deref().unwrap_or("unknown")
            );
        } else {
            log::info!(
                "Port check: service={}, port={}, status=stopped",
                status.name,
                status.port
            );
        }
    }
    log::info!("=== End Service Status ===");
}

/// Kill any process holding a specific port.
/// Returns true if something was killed, false if port was already free.
pub fn kill_port_owner(port: u16) -> bool {
    let status = check_port(port);
    if !status.in_use {
        return false;
    }

    if let Some(pid) = status.pid {
        log::warn!(
            "Killing stale process: service={}, port={}, pid={}, process={}",
            status.name,
            port,
            pid,
            status.process_name.as_deref().unwrap_or("unknown")
        );

        let killed = if cfg!(windows) {
            Command::new("taskkill")
                .args(["/F", "/PID", &pid.to_string()])
                .output()
        } else {
            Command::new("kill")
                .args(["-9", &pid.to_string()])
                .output()
        };

        match killed {
            Ok(output) => {
                if output.status.success() {
                    log::info!(
                        "Successfully killed stale process: service={}, port={}, pid={}",
                        status.name,
                        port,
                        pid
                    );
                    true
                } else {
                    log::error!(
                        "Failed to kill stale process: service={}, port={}, pid={}, stderr={}",
                        status.name,
                        port,
                        pid,
                        String::from_utf8_lossy(&output.stderr)
                    );
                    false
                }
            }
            Err(e) => {
                log::error!(
                    "Failed to execute kill command: service={}, port={}, pid={}, error={}",
                    status.name,
                    port,
                    pid,
                    e
                );
                false
            }
        }
    } else {
        false
    }
}

/// Kill all stale processes on **Tauri-managed** ports only.
///
/// This intentionally excludes OpenWA (port 2785) — the user runs it
/// manually via Docker. Killing docker-proxy.exe would disconnect the
/// container's port mapping, requiring a Docker restart to recover.
pub fn kill_all_stale() {
    for port in &MANAGED_PORTS {
        kill_port_owner(*port);
    }
}

/// Ensure a port is free, killing the owner if necessary.
/// Returns Ok(()) if the port is free, Err with details if kill failed.
pub fn ensure_port_free(port: u16) -> Result<(), String> {
    if kill_port_owner(port) {
        // Give the OS a moment to release the port
        std::thread::sleep(std::time::Duration::from_millis(500));

        // Verify it's actually free now
        let status = check_port(port);
        if status.in_use {
            return Err(format!(
                "Port {} is still in use after killing PID {:?}",
                port, status.pid
            ));
        }
    }
    Ok(())
}

/// Get a human-readable service name for a port.
fn service_name_for(port: u16) -> String {
    match port {
        BACKEND_PORT => "uvicorn (backend)".to_string(),
        BAILEYS_PORT => "Baileys (WhatsApp gateway)".to_string(),
        BAILEYS_WS_PORT => "Baileys WebSocket".to_string(),
        2785 => "OpenWA (WhatsApp bridge — Docker)".to_string(),
        _ => format!("unknown service on port {}", port),
    }
}

/// Windows: use `netstat -ano | findstr :PORT` to find the PID.
fn check_port_windows(port: u16) -> (bool, Option<u32>, Option<String>) {
    let output = match Command::new("netstat")
        .args(["-ano"])
        .output()
    {
        Ok(o) => o,
        Err(_) => return (false, None, None),
    };

    let stdout = String::from_utf8_lossy(&output.stdout);
    let port_str = format!(":{}", port);

    for line in stdout.lines() {
        if line.contains(&port_str) && line.contains("LISTENING") {
            // Parse: "TCP    127.0.0.1:18234    0.0.0.0:0    LISTENING    1234"
            let parts: Vec<&str> = line.split_whitespace().collect();
            if let Some(pid_str) = parts.last() {
                if let Ok(pid) = pid_str.parse::<u32>() {
                    let process_name = get_process_name_windows(pid);
                    return (true, Some(pid), process_name);
                }
            }
        }
    }

    (false, None, None)
}

/// Unix: use `lsof -ti :PORT` to find the PID.
/// Correctly interpolates the port number (was a string-literal bug before).
fn check_port_unix(port: u16) -> (bool, Option<u32>, Option<String>) {
    let lsof_arg = format!("-ti:{}", port);
    let output = match Command::new("lsof")
        .args([&lsof_arg])
        .output()
    {
        Ok(o) => o,
        Err(_) => return (false, None, None),
    };

    let stdout = String::from_utf8_lossy(&output.stdout);
    if let Some(first_line) = stdout.lines().next() {
        if let Ok(pid) = first_line.trim().parse::<u32>() {
            let process_name = get_process_name_unix(pid);
            return (true, Some(pid), process_name);
        }
    }

    (false, None, None)
}

/// Get process name by PID on Windows using `tasklist`.
fn get_process_name_windows(pid: u32) -> Option<String> {
    let output = Command::new("tasklist")
        .args(["/FI", &format!("PID eq {}", pid), "/FO", "CSV", "/NH"])
        .output()
        .ok()?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    // CSV format: "python.exe","1234","Console","1","164,880 K"
    if let Some(first_line) = stdout.lines().next() {
        if let Some(name) = first_line.split(',').next() {
            return Some(name.trim_matches('"').to_string());
        }
    }

    None
}

/// Get process name by PID on Unix using `ps`.
fn get_process_name_unix(pid: u32) -> Option<String> {
    let output = Command::new("ps")
        .args(["-p", &pid.to_string(), "-o", "comm="])
        .output()
        .ok()?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    Some(stdout.trim().to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_check_port_returns_status() {
        // Port 1 should be free on most systems
        let status = check_port(1);
        assert_eq!(status.port, 1);
        assert_eq!(status.name, "unknown service on port 1");
    }

    #[test]
    fn test_service_name_for_known_ports() {
        assert_eq!(service_name_for(BACKEND_PORT), "uvicorn (backend)");
        assert_eq!(service_name_for(BAILEYS_PORT), "Baileys (WhatsApp gateway)");
        assert_eq!(service_name_for(BAILEYS_WS_PORT), "Baileys WebSocket");
    }

    #[test]
    fn test_managed_ports_includes_baileys() {
        assert!(
            MANAGED_PORTS.contains(&BAILEYS_PORT),
            "Baileys port must be in MANAGED_PORTS"
        );
        assert!(
            MANAGED_PORTS.contains(&BAILEYS_WS_PORT),
            "Baileys WebSocket port must be in MANAGED_PORTS"
        );
    }
}
