import { useEffect, useRef } from "react";
import { useWhatsAppStore } from "../stores/whatsapp";

const HTTP_URL = "http://127.0.0.1:2786";

/**
 * Polls Baileys sidecar status + QR via HTTP every 2s, and also connects
 * to the WebSocket for live updates.
 *
 * The HTTP polling is the primary channel — the WS is opportunistic.
 * In the production Tauri WebView (https://tauri.localhost) WebSocket
 * connections to ws://127.0.0.1 may be blocked as mixed content, so you
 * can't rely on WS alone.
 */
export function useBaileysWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptsRef = useRef(0);

  const { setStatus, setQr, clearQr, setSidecarOnline } =
    useWhatsAppStore();

  useEffect(() => {
    let cancelled = false;

    // ── WebSocket (best-effort) ─────────────────────────────────────
    function connectWS() {
      const ws = new WebSocket("ws://127.0.0.1:2787");
      wsRef.current = ws;

      ws.onopen = () => {
        attemptsRef.current = 0;
        setSidecarOnline(true);
      };

      ws.onmessage = (event) => {
        try {
          const d = JSON.parse(event.data);
          if (d.event === "qr") {
            setQr(d.qrImage, d.qrData);
          } else if (d.event === "status") {
            mapStatus(d.status);
          }
        } catch {
          /* ignore */
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        attemptsRef.current += 1;
        const delay = Math.min(1000 * 2 ** attemptsRef.current, 30_000);
        retryRef.current = setTimeout(connectWS, delay);
      };

      ws.onerror = () => ws.close();
    }

    // ── Status mapping (used by both WS and HTTP poll) ──────────────
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
        // "connecting", "disconnected", or anything else — preserve as-is
        setStatus(s as any);
      }
    }

    // ── HTTP poll ───────────────────────────────────────────────────
    async function poll() {
      if (cancelled) return;
      try {
        const r = await fetch(`${HTTP_URL}/status`);
        const data = await r.json();
        setSidecarOnline(true);
        mapStatus(data.status);

        // If status is "qr", also grab the QR image via HTTP
        if (data.status === "qr") {
          const qrResp = await fetch(`${HTTP_URL}/qr`);
          const qrData = await qrResp.json();
          if (qrData.qrImage) {
            setQr(qrData.qrImage, qrData.qrData ?? "");
          }
        }
      } catch {
        setSidecarOnline(false);
      }
    }

    // ── Start ──────────────────────────────────────────────────────
    // Fire immediately, then every 2s
    poll();
    pollRef.current = setInterval(poll, 2000);

    connectWS();

    return () => {
      cancelled = true;
      if (wsRef.current) wsRef.current.close();
      if (retryRef.current) clearTimeout(retryRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
