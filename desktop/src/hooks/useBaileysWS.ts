import { useEffect, useRef } from "react";
import { useWhatsAppStore } from "../stores/whatsapp";

const WS_URL = "ws://127.0.0.1:2787";

/**
 * Connects to the Baileys sidecar WebSocket and updates the WhatsApp store
 * with live QR codes and connection status.
 *
 * Automatically reconnects on disconnect with exponential backoff.
 */
export function useBaileysWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptsRef = useRef(0);

  const {
    setStatus,
    setQr,
    clearQr,
    setJid,
    setSidecarOnline,
  } = useWhatsAppStore();

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptsRef.current = 0;
        setSidecarOnline(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          switch (data.event) {
            case "qr":
              setQr(data.qrImage, data.qrData);
              break;

            case "status":
              if (data.status === "open") {
                setStatus("connected");
                clearQr();
              } else if (data.status === "close") {
                setStatus("disconnected");
              } else if (data.status === "loggedOut") {
                setStatus("loggedOut");
                clearQr();
              } else {
                setStatus(data.status);
              }
              break;
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        wsRef.current = null;

        // Auto-reconnect with exponential backoff (max 30s)
        attemptsRef.current += 1;
        const delay = Math.min(1000 * 2 ** attemptsRef.current, 30_000);

        retryRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    // Fetch initial status from HTTP endpoint (faster than waiting for WS).
    // The WebView can mount before the sidecar is bound, so retry with
    // backoff until it answers — otherwise sidecarOnline gets stuck false.
    // After fast retries exhaust, fall back to a slow background poll so a
    // late-arriving sidecar still gets picked up.
    let slowPoll: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    function applyStatus(data: { status: string; jid?: string | null }) {
      if (data.status === "open") {
        setStatus("connected");
        if (data.jid) setJid(data.jid);
      } else if (data.status === "qr") {
        // QR will come via WebSocket
        setStatus("qr");
      } else {
        setStatus("disconnected");
      }
      setSidecarOnline(true);
    }

    function fetchInitialStatus(attempts = 0) {
      if (cancelled) return;
      fetch("http://127.0.0.1:2786/status")
        .then((r) => r.json())
        .then(applyStatus)
        .catch(() => {
          if (cancelled) return;
          if (attempts < 20) {
            // 20 × 500ms = 10s ceiling — well past the sidecar's 30s ready
            // timeout we expect during a cold start.
            setTimeout(() => fetchInitialStatus(attempts + 1), 500);
          } else {
            setSidecarOnline(false);
            // Slow background poll — keeps checking every 3s until the
            // sidecar answers, so a late-bound sidecar still flips the UI.
            slowPoll = setTimeout(() => fetchInitialStatus(0), 3000);
          }
        });
    }
    fetchInitialStatus();

    connect();

    return () => {
      cancelled = true;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (retryRef.current) {
        clearTimeout(retryRef.current);
      }
      if (slowPoll) {
        clearTimeout(slowPoll);
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
