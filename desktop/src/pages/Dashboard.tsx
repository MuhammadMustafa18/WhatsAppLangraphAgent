import { useEffect, useState } from "react";
import { listProviders } from "../api/providers";
import { listPersonas } from "../api/personas";
import { useWhatsAppStore } from "../stores/whatsapp";
import { useBaileysWebSocket } from "../hooks/useBaileysWS";

interface Counts {
  providers: number;
  personas: number;
  loading: boolean;
  error: string | null;
}

export default function Dashboard() {
  // Connect to Baileys WebSocket for live WhatsApp status
  useBaileysWebSocket();

  const { status: waStatus, jid, sidecarOnline } = useWhatsAppStore();

  const [counts, setCounts] = useState<Counts>({
    providers: 0,
    personas: 0,
    loading: true,
    error: null,
  });

  useEffect(() => {
    async function load() {
      try {
        const [providers, personas] = await Promise.all([
          listProviders(),
          listPersonas(),
        ]);
        setCounts({
          providers: providers.length,
          personas: personas.length,
          loading: false,
          error: null,
        });
      } catch (e) {
        setCounts((c) => ({
          ...c,
          loading: false,
          error: e instanceof Error ? e.message : String(e),
        }));
      }
    }
    load();
  }, []);

  const ready = !counts.loading && counts.providers > 0 && counts.personas > 0;

  // WhatsApp connection status dot
  const waDot = !sidecarOnline
    ? "bg-gray-500"
    : waStatus === "connected"
      ? "bg-green-500"
      : waStatus === "qr" || waStatus === "connecting"
        ? "bg-yellow-500"
        : "bg-red-500";

  const waLabel = !sidecarOnline
    ? "Offline"
    : waStatus === "connected"
      ? "Connected"
      : waStatus === "qr"
        ? "Scan QR"
        : waStatus === "connecting"
          ? "Connecting..."
          : "Disconnected";

  const displayJid = jid
    ? jid.replace(/@.*$/, "").replace(/(\d{2})(\d{3})(\d{3})(\d{4})/, "+$1 $2 $3 $4")
    : null;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      {counts.error && (
        <div className="bg-red-500/20 border border-red-500 text-red-300 p-3 rounded mb-4 text-sm">
          {counts.error}
        </div>
      )}

      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-gray-800 p-4 rounded-lg">
          <h2 className="text-gray-400 text-sm">Providers</h2>
          <p className="text-3xl font-bold">
            {counts.loading ? "—" : counts.providers}
          </p>
          <a href="/providers" className="text-blue-400 text-sm hover:underline">
            {counts.providers === 0 ? "Add one →" : "Manage →"}
          </a>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg">
          <h2 className="text-gray-400 text-sm">Personas</h2>
          <p className="text-3xl font-bold">
            {counts.loading ? "—" : counts.personas}
          </p>
          <a href="/personas" className="text-blue-400 text-sm hover:underline">
            {counts.personas === 0 ? "Add one →" : "Manage →"}
          </a>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="flex items-center gap-2 mb-1">
            <span className={`w-2.5 h-2.5 rounded-full ${waDot}`} />
            <h2 className="text-gray-400 text-sm">WhatsApp</h2>
          </div>
          <p className="text-3xl font-bold">{waLabel}</p>
          {displayJid && (
            <p className="text-gray-500 text-xs mt-1 font-mono">{displayJid}</p>
          )}
          <a href="/connections" className="text-blue-400 text-sm hover:underline">
            {waStatus === "connected" ? "Details →" : "Connect →"}
          </a>
        </div>
      </div>

      {!counts.loading && !ready && (
        <div className="bg-gray-800 p-6 rounded-lg border border-yellow-600/40">
          <h2 className="text-lg font-bold mb-2">Setup checklist</h2>
          <ul className="text-gray-300 text-sm space-y-1">
            {counts.providers === 0 && (
              <li>
                ☐ Add an LLM provider (OpenAI, Anthropic, or OpenAI-compatible).
                <a href="/providers" className="text-blue-400 hover:underline ml-2">
                  Providers →
                </a>
              </li>
            )}
            {counts.personas === 0 && (
              <li>
                ☐ Create at least one persona (system prompt + optional knowledge
                base).
                <a href="/personas" className="text-blue-400 hover:underline ml-2">
                  Personas →
                </a>
              </li>
            )}
            <li>
              ☐{' '}
              <a href="/connections" className="text-blue-400 hover:underline">
                Connect WhatsApp
              </a>
              {" "}— scan the QR code in the Connections page.
            </li>
          </ul>
        </div>
      )}

      {ready && (
        <div className="bg-gray-800 p-6 rounded-lg border border-green-600/40">
          <h2 className="text-lg font-bold mb-2 text-green-300">Ready</h2>
          <p className="text-gray-300 text-sm">
            Bot is configured. Send a WhatsApp message to your connected number
            — the bot will reply using your default persona. Use slash prefixes
            (<code className="bg-gray-700 px-1 rounded">/support</code>,{" "}
            <code className="bg-gray-700 px-1 rounded">/booking</code>, etc.) to
            switch personas on the fly.
          </p>
        </div>
      )}
    </div>
  );
}