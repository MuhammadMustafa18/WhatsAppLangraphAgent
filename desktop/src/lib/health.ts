// Single source of truth for sidecar endpoints and a tiny health-poll helper.
// Both sidecars are spawned by the Tauri Rust process; the WebView only knows
// them by URL. Keep these in sync with src-tauri/src/port_check.rs.

export const BACKEND_URL = "http://127.0.0.1:18234";
export const BAILEYS_URL = "http://127.0.0.1:2786";
export const BAILEYS_WS_URL = "ws://127.0.0.1:2787";

export type SidecarId = "backend" | "baileys";

export const SIDECARS: Record<SidecarId, { label: string; url: string }> = {
  backend: { label: "API server", url: `${BACKEND_URL}/health` },
  baileys: { label: "WhatsApp gateway", url: `${BAILEYS_URL}/health` },
};

// Poll a sidecar's /health until it returns 2xx, the abort signal fires, or
// the timeout elapses. Resolves with "ok"; rejects with "timeout" on deadline.
export function waitForHealthy(
  url: string,
  signal: AbortSignal,
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
        const res = await fetch(url);
        if (res.ok) {
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
