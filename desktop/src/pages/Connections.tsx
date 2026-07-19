import { useBaileysWebSocket } from "../hooks/useBaileysWS";
import { useWhatsAppStore, ConnectionStatus } from "../stores/whatsapp";

const STATUS_LABELS: Record<ConnectionStatus, { text: string; color: string; icon: string }> = {
  disconnected: {
    text: "Disconnected — waiting for sidecar...",
    color: "text-yellow-400",
    icon: "⏳",
  },
  qr: {
    text: "Scan QR with WhatsApp to link your account",
    color: "text-blue-400",
    icon: "📱",
  },
  connecting: {
    text: "Connecting...",
    color: "text-yellow-400",
    icon: "🔄",
  },
  connected: {
    text: "WhatsApp connected and ready",
    color: "text-green-400",
    icon: "✅",
  },
  loggedOut: {
    text: "Logged out — scan the QR again to reconnect",
    color: "text-red-400",
    icon: "🔴",
  },
};

export default function Connections() {
  // This hook handles the WebSocket connection lifecycle internally
  useBaileysWebSocket();

  const { status, qrImage, jid, sidecarOnline } = useWhatsAppStore();
  const info = STATUS_LABELS[status];

  // Format JID for display (e.g. "92317...@s.whatsapp.net" → "+92 317 XXX XXXX")
  const displayJid = jid
    ? jid.replace(/@.*$/, "").replace(/(\d{2})(\d{3})(\d{3})(\d{4})/, "+$1 $2 $3 $4")
    : null;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">WhatsApp Connection</h1>
      </div>

      {/* Sidecar status bar */}
      <div
        className={`p-3 rounded-lg mb-6 text-sm border ${
          sidecarOnline
            ? "bg-green-500/10 border-green-500/30 text-green-300"
            : "bg-red-500/10 border-red-500/30 text-red-300"
        }`}
      >
        {sidecarOnline
          ? "● Baileys gateway is running"
          : "○ Baileys gateway is offline — try restarting the app"}
      </div>

      {/* Main connection card */}
      <div className="bg-gray-800 rounded-xl p-8 max-w-lg mx-auto">
        <div className="text-center">
          {/* Status icon */}
          <div className="text-5xl mb-4">{info.icon}</div>

          {/* Status text */}
          <p className={`text-lg font-semibold mb-2 ${info.color}`}>
            {info.text}
          </p>

          {/* Connected phone number */}
          {status === "connected" && displayJid && (
            <p className="text-gray-400 text-sm mb-4">
              Linked to <span className="text-white font-mono">{displayJid}</span>
            </p>
          )}

          {/* QR code */}
          {status === "qr" && qrImage && (
            <div className="my-6">
              <div className="bg-white p-4 rounded-xl inline-block shadow-lg">
                <img
                  src={qrImage}
                  alt="WhatsApp QR Code"
                  className="w-80 h-80 md:w-96 md:h-96"
                />
                <p className="text-gray-400 text-xs mt-2">
                  QR code refreshes every ~20 seconds. If scan fails, wait for the next one.
                </p>
              </div>
              <p className="text-gray-500 text-xs mt-3">
                Open WhatsApp → Settings → Linked Devices → Link a Device
              </p>
            </div>
          )}

          {/* Spinner during connecting */}
          {status === "connecting" && (
            <div className="my-6 flex justify-center">
              <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {/* Logged out prompt */}
          {status === "loggedOut" && (
            <p className="text-gray-400 text-sm mt-2">
              The QR code should appear shortly. If it doesn't, restart the app.
            </p>
          )}

          {/* Disconnected / no QR yet */}
          {status === "disconnected" && !qrImage && (
            <div className="my-6 flex justify-center">
              <div className="w-12 h-12 border-4 border-gray-600 border-t-gray-400 rounded-full animate-spin" />
            </div>
          )}
        </div>
      </div>

      {/* Help section */}
      <div className="bg-gray-800/50 rounded-lg p-5 max-w-lg mx-auto mt-4 border border-gray-700/50">
        <h3 className="text-sm font-semibold text-gray-300 mb-2">
          How linking works
        </h3>
        <ol className="text-gray-500 text-xs space-y-1.5 list-decimal list-inside">
          <li>A QR code appears above when the gateway is ready</li>
          <li>Open WhatsApp on your phone</li>
          <li>Tap the menu (⋮) → Linked Devices → Link a Device</li>
          <li>Scan the QR code shown above</li>
          <li>
            The gateway saves your session — you won't need to scan again
          </li>
        </ol>
      </div>
    </div>
  );
}
