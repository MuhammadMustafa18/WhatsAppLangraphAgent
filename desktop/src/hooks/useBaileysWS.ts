import { useEffect, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useWhatsAppStore } from "../stores/whatsapp";

/**
 * Polls Baileys sidecar status + QR via Tauri IPC (avoids mixed-content
 * blocking in production builds where the origin is https://tauri.localhost),
 * and also listens for live updates relayed through the Rust WebSocket proxy.
 *
 * The IPC polling is the primary channel — the event listener is opportunistic.
 * Both bypass the browser's mixed-content policy because the requests originate
 * from the Rust process, not the WebView.
 */
export function useBaileysWebSocket() {
  const unlistenRef = useRef<(() => void) | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { setStatus, setQr, clearQr, setSidecarOnline, setJid } =
    useWhatsAppStore();

  useEffect(() => {
    let cancelled = false;

    // ── Status mapping (used by both event listener and IPC poll) ─────
    function mapStatus(s: string) {
      if (s === "open") {
        setStatus("connected");
        clearQr();
      } else if (s === "close") {
        setStatus("disconnected");
      } else if (s === "loggedOut") {
        setStatus("loggedOut");
        clearQr();
      } else if (s === "qr") {
        setStatus("qr");
      } else {
        setStatus(s as any);
      }
    }

    // ── Tauri event listener (best-effort, relayed by Rust) ───────────
    async function setupEventListener() {
      try {
        const unlisten = await listen<string>("baileys-ws-event", (event) => {
          if (cancelled) return;
          try {
            const d = JSON.parse(event.payload);
            if (d.event === "qr" && d.qrImage) {
              setQr(d.qrImage, d.qrData ?? "");
            } else if (d.event === "status") {
              mapStatus(d.status);
            }
          } catch {
            /* ignore */
          }
        });
        unlistenRef.current = unlisten;
        setSidecarOnline(true);
      } catch {
        // Not running inside Tauri — no-op
      }
    }

    // ── IPC poll ──────────────────────────────────────────────────────
    async function poll() {
      if (cancelled) return;
      try {
        const raw: string = await invoke("baileys_proxy", { path: "/health" });
        const data = JSON.parse(raw);
        setSidecarOnline(true);
        mapStatus(data.connection);

        // Fetch QR whenever the server says it has one
        if (data.hasQr) {
          const qrRaw: string = await invoke("baileys_proxy", { path: "/qr" });
          const qrData = JSON.parse(qrRaw);
          if (qrData.qrImage) {
            setQr(qrData.qrImage, qrData.qrData ?? "");
          }
        }

        // Also fetch JID if connected
        if (data.connection === "open") {
          const statusRaw: string = await invoke("baileys_proxy", { path: "/status" });
          const statusData = JSON.parse(statusRaw);
          if (statusData.jid) {
            setJid(statusData.jid);
          }
        }
      } catch {
        setSidecarOnline(false);
      }
    }

    // ── Start ─────────────────────────────────────────────────────────
    setupEventListener();
    poll();
    pollRef.current = setInterval(poll, 2000);

    return () => {
      cancelled = true;
      if (unlistenRef.current) unlistenRef.current();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
