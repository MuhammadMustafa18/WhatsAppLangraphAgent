// Single source of truth for sidecar endpoints and a tiny health-poll helper.
// Both sidecars are spawned by the Tauri Rust process; the WebView only knows
// them by URL. Keep these in sync with src-tauri/src/port_check.rs.
//
// In production builds (https://tauri.localhost), direct HTTP to 127.0.0.1 is
// blocked as mixed content. We route all sidecar requests through Tauri IPC
// commands that the Rust process handles, bypassing the browser restriction.

import { invoke } from "@tauri-apps/api/core";

export const BACKEND_URL = "http://127.0.0.1:18234";
export const BAILEYS_URL = "http://127.0.0.1:2786";
export const BAILEYS_WS_URL = "ws://127.0.0.1:2787";

export type SidecarId = "backend" | "baileys";

/** Payload emitted by the Rust sidecar process on error. */
export interface SidecarErrorPayload {
  id: SidecarId;
  error: string;
}

export const SIDECARS: Record<SidecarId, { label: string }> = {
  backend: { label: "API server" },
  baileys: { label: "WhatsApp gateway" },
};

/**
 * Listen for `sidecar-error` events emitted by the Rust backend.
 * Returns an unlisten function. Safe to call in browser dev mode
 * (Tauri APIs won't be available, returns a no-op).
 */
export async function listenForSidecarErrors(
  handler: (payload: SidecarErrorPayload) => void,
): Promise<() => void> {
  try {
    const { listen } = await import("@tauri-apps/api/event");
    return listen<SidecarErrorPayload>("sidecar-error", (event) => {
      handler(event.payload);
    });
  } catch {
    // Not running inside Tauri (e.g. browser dev mode) — no-op
    return () => {};
  }
}

/**
 * Poll a sidecar's /health endpoint until it returns OK, the abort signal
 * fires, or the timeout elapses.
 *
 * Uses Tauri IPC (`invoke("proxy_health", ...)`) so it works in both dev and
 * production builds without mixed-content issues.
 */
export function waitForHealthy(
  _url: string, // kept for API compat; ignored in favour of IPC
  signal: AbortSignal,
  sidecarId: SidecarId,
  timeoutMs = 30_000,
  intervalMs = 500,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const deadline = setTimeout(() => {
      cleanup();
      reject(new Error("timeout"));
    }, timeoutMs);

    const onAbort = () => {
      cleanup();
      reject(new Error("aborted"));
    };

    function cleanup() {
      clearTimeout(deadline);
      signal.removeEventListener("abort", onAbort);
    }

    signal.addEventListener("abort", onAbort);

    const tick = async () => {
      if (signal.aborted) return;
      try {
        const raw: string = await invoke("proxy_health", { sidecarId });
        const data = JSON.parse(raw);
        if (data.status === "ok") {
          cleanup();
          resolve();
          return;
        }
      } catch {
        // not ready yet — keep polling
      }
      if (!signal.aborted) setTimeout(tick, intervalMs);
    };

    tick();
  });
}
