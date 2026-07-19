import { useState } from "react";
import { useBaileysWebSocket } from "../hooks/useBaileysWS";
import { useWhatsAppStore, ConnectionStatus } from "../stores/whatsapp";

// Direct to Baileys sidecar (port 2786), not via the FastAPI backend (18234).
const BAILEYS_URL = "http://127.0.0.1:2786";

const STATUS_LABELS: Record<
  ConnectionStatus,
  { text: string; tone: "ok" | "wait" | "warn" | "err" }
> = {
  disconnected: { text: "Disconnected — waiting for sidecar", tone: "wait" },
  qr: { text: "Scan QR with WhatsApp to link your account", tone: "wait" },
  connecting: { text: "Connecting", tone: "wait" },
  connected: { text: "WhatsApp connected and ready", tone: "ok" },
  loggedOut: { text: "Logged out — scan the QR again to reconnect", tone: "err" },
};

const TONE_DOT: Record<"ok" | "wait" | "warn" | "err", string> = {
  ok: "bg-deep-green",
  wait: "bg-coral",
  warn: "bg-coral",
  err: "bg-error",
};

export default function Connections() {
  // This hook handles the WebSocket connection lifecycle internally
  useBaileysWebSocket();

  const { status, qrImage, jid, sidecarOnline, reset } = useWhatsAppStore();
  const info = STATUS_LABELS[status];

  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  async function handleLogout() {
    setLoggingOut(true);
    setLogoutError(null);
    try {
      const res = await fetch(`${BAILEYS_URL}/logout`, { method: "POST" });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      // Optimistically clear local state — the WS will also push "loggedOut"
      // and a fresh QR, but resetting here avoids a stale "Connected" flicker.
      reset();
    } catch (err) {
      setLogoutError(
        err instanceof Error ? err.message : "Couldn't reach the WhatsApp gateway.",
      );
    } finally {
      setLoggingOut(false);
      setConfirming(false);
    }
  }

  // Format JID for display (e.g. "92317...@s.whatsapp.net" → "+92 317 XXX XXXX")
  const displayJid = jid
    ? jid.replace(/@.*$/, "").replace(/(\d{2})(\d{3})(\d{3})(\d{4})/, "+$1 $2 $3 $4")
    : null;

  const isConnected = status === "connected";

  return (
    <div>
      {/* Hero declaration */}
      <div className="mb-section flex items-start justify-between gap-12">
        <div>
          <p className="mono-label text-muted mb-3">Integrations</p>
          <h1 className="font-display text-section-heading text-ink">
            WhatsApp connection
          </h1>
        </div>

        {isConnected && !confirming && (
          <button
            onClick={() => {
              setLogoutError(null);
              setConfirming(true);
            }}
            className="btn-pill-outline shrink-0"
          >
            Sign out of WhatsApp
          </button>
        )}

        {isConnected && confirming && (
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-caption text-body-muted">
              Unlink this device?
            </span>
            <button
              onClick={() => setConfirming(false)}
              disabled={loggingOut}
              className="btn-pill-outline disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleLogout}
              disabled={loggingOut}
              className="btn-primary disabled:opacity-50"
            >
              {loggingOut ? "Signing out…" : "Confirm"}
            </button>
          </div>
        )}
      </div>

      {logoutError && (
        <div className="mb-8 max-w-2xl border border-error/30 bg-error/5 px-4 py-3 text-caption text-error rounded-sm">
          Sign-out failed: {logoutError}
        </div>
      )}

      {/* Sidecar status — trust strip / observability row */}
      <div
        className={`mb-section flex items-center gap-3 px-4 py-3 border rounded-sm ${
          sidecarOnline
            ? "border-card-border bg-canvas"
            : "border-error/30 bg-error/5"
        }`}
      >
        <span
          className={`h-2 w-2 rounded-full ${
            sidecarOnline ? "bg-deep-green" : "bg-error"
          }`}
        />
        <p className="mono-label">
          {sidecarOnline
            ? "Baileys gateway is running"
            : "Baileys gateway is offline — try restarting the app"}
        </p>
      </div>

      {/* Connected band — dark green when active, white card when not */}
      {isConnected && displayJid ? (
        <section className="dark-band mb-section">
          <p className="mono-label text-on-dark/70 mb-3">Active device</p>
          <h2 className="font-display text-product-display text-on-dark mb-4">
            Linked to {displayJid}
          </h2>
          <p className="text-body-large text-on-dark/80 max-w-xl">
            Inbound messages are forwarded to your configured backend. Outbound
            replies route through this gateway.
          </p>
        </section>
      ) : (
        <section className="bg-canvas border border-card-border rounded-md p-8 mb-section">
          <div className="text-center max-w-md mx-auto">
            {/* Status chip */}
            <div className="inline-flex items-center gap-2 mb-6">
              <span
                className={`h-2 w-2 rounded-full ${TONE_DOT[info.tone]}`}
              />
              <span className="mono-label text-muted">{info.text}</span>
            </div>

            {/* QR code — hero-photo-card treatment */}
            {status === "qr" && qrImage && (
              <>
                <div className="my-8 inline-block bg-canvas border border-card-border rounded-lg p-6 shadow-media-lift">
                  <img
                    src={qrImage}
                    alt="WhatsApp QR Code"
                    className="w-72 h-72 md:w-80 md:h-80"
                  />
                </div>
                <p className="text-caption text-body-muted">
                  The QR refreshes every ~20 seconds. If scan fails, wait for
                  the next one.
                </p>
                <p className="mono-label text-muted mt-3">
                  Open WhatsApp · Linked Devices · Link a Device
                </p>
              </>
            )}

            {/* Spinner states */}
            {(status === "connecting" ||
              (status === "disconnected" && !qrImage)) && (
              <div className="my-8 flex justify-center">
                <div className="h-12 w-12 rounded-full border-2 border-hairline border-t-primary animate-spin" />
              </div>
            )}

            {status === "loggedOut" && (
              <p className="text-caption text-body-muted mt-4">
                The QR code should appear shortly. If it doesn't, restart the
                app.
              </p>
            )}
          </div>
        </section>
      )}

      {/* Help section — rule-separated list, no boxing */}
      <section className="border-t border-hairline pt-section">
        <p className="mono-label text-muted mb-3">How linking works</p>
        <ol className="divide-y divide-hairline border-y border-hairline">
          <HelpRow n="1" title="A QR code appears above when the gateway is ready." />
          <HelpRow n="2" title="Open WhatsApp on your phone." />
          <HelpRow n="3" title="Tap the menu (⋮) → Linked Devices → Link a Device." />
          <HelpRow n="4" title="Scan the QR code shown above." />
          <HelpRow
            n="5"
            title="The gateway saves your session — you won't need to scan again."
          />
        </ol>
      </section>
    </div>
  );
}

function HelpRow({ n, title }: { n: string; title: string }) {
  return (
    <li className="py-5 flex items-center gap-8">
      <span className="font-mono text-mono-label text-muted w-6 shrink-0">
        {n}
      </span>
      <span className="text-body-large text-ink">{title}</span>
    </li>
  );
}
