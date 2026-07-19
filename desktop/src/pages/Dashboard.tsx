import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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

  // WhatsApp connection state → chip color
  const waTone = !sidecarOnline
    ? "muted"
    : waStatus === "connected"
      ? "deep-green"
      : waStatus === "qr" || waStatus === "connecting"
        ? "coral"
        : "error";

  const waLabel = !sidecarOnline
    ? "Offline"
    : waStatus === "connected"
      ? "Connected"
      : waStatus === "qr"
        ? "Scan QR"
        : waStatus === "connecting"
          ? "Connecting"
          : "Disconnected";

  const dotClass = {
    muted: "bg-muted",
    "deep-green": "bg-deep-green",
    coral: "bg-coral",
    error: "bg-error",
  }[waTone];

  const displayJid = jid
    ? jid.replace(/@.*$/, "").replace(/(\d{2})(\d{3})(\d{3})(\d{4})/, "+$1 $2 $3 $4")
    : null;

  return (
    <div>
      {/* Hero declaration — Cohere opens on a tight display headline */}
      <div className="mb-section">
        <p className="mono-label text-muted mb-3">Overview</p>
        <h1 className="font-display text-section-heading text-ink mb-4">
          Your WhatsApp command center
        </h1>
        <p className="text-body-large text-body-muted max-w-2xl">
          Connect an LLM provider, define a persona, and link WhatsApp. The bot
          replies on your behalf using the slash-prefixed persona of your
          choice.
        </p>
      </div>

      {counts.error && (
        <div className="border border-error/30 bg-error/5 text-error px-4 py-3 mb-8 text-caption rounded-sm">
          {counts.error}
        </div>
      )}

      {/* Capability-card grid — 3 columns on desktop, 1 on mobile */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-section">
        <CapabilityCard
          label="Providers"
          value={counts.loading ? "—" : counts.providers}
          cta={counts.providers === 0 ? "Add one" : "Manage"}
          ctaHref="/providers"
        />
        <CapabilityCard
          label="Personas"
          value={counts.loading ? "—" : counts.personas}
          cta={counts.personas === 0 ? "Create one" : "Manage"}
          ctaHref="/personas"
        />

        <div className="bg-canvas border border-card-border rounded-md p-6">
          <div className="flex items-center gap-2 mb-3">
            <span className={`h-2 w-2 rounded-full ${dotClass}`} />
            <p className="mono-label text-muted">WhatsApp</p>
          </div>
          <p className="font-display text-section-heading text-ink">
            {waLabel}
          </p>
          {displayJid && (
            <p className="font-mono text-mono-label text-muted mt-3">
              {displayJid}
            </p>
          )}
          <Link
            to="/connections"
            className="btn-secondary mt-6 inline-flex"
          >
            {waStatus === "connected" ? "Manage connection" : "Connect now"}
          </Link>
        </div>
      </div>

      {/* Setup checklist — only when something is missing */}
      {!counts.loading && !ready && (
        <section className="border-t border-hairline pt-section">
          <p className="mono-label text-muted mb-3">Setup</p>
          <h2 className="font-display text-card-heading text-ink mb-6">
            A few things to wire up
          </h2>
          <ul className="divide-y divide-hairline border-y border-hairline">
            {counts.providers === 0 && (
              <SetupRow
                title="Add an LLM provider"
                body="OpenAI, Anthropic, or any OpenAI-compatible endpoint."
                cta="Providers"
                ctaHref="/providers"
              />
            )}
            {counts.personas === 0 && (
              <SetupRow
                title="Create at least one persona"
                body="System prompt plus an optional knowledge base."
                cta="Personas"
                ctaHref="/personas"
              />
            )}
            <SetupRow
              title="Link your WhatsApp device"
              body="Scan the QR code from the Connections page."
              cta="Connections"
              ctaHref="/connections"
            />
          </ul>
        </section>
      )}

      {/* Ready band — full-width dark green when everything is wired */}
      {ready && (
        <section className="dark-band mt-section">
          <p className="mono-label text-on-dark/70 mb-3">Live</p>
          <h2 className="font-display text-card-heading text-on-dark mb-3">
            You're ready to receive messages.
          </h2>
          <p className="text-body-large text-on-dark/80 max-w-2xl">
            Send a WhatsApp message to your connected number — the bot will
            reply using your default persona. Use slash prefixes
            (<code className="font-mono text-mono-label bg-cohere-black/40 px-2 py-0.5 rounded-xs">/support</code>,{" "}
            <code className="font-mono text-mono-label bg-cohere-black/40 px-2 py-0.5 rounded-xs">/booking</code>, …)
            to switch personas on the fly.
          </p>
        </section>
      )}
    </div>
  );
}

function CapabilityCard({
  label,
  value,
  cta,
  ctaHref,
}: {
  label: string;
  value: number | string;
  cta: string;
  ctaHref: string;
}) {
  return (
    <div className="bg-canvas border border-card-border rounded-md p-6">
      <p className="mono-label text-muted mb-3">{label}</p>
      <p className="font-display text-section-heading text-ink">{value}</p>
      <Link to={ctaHref} className="btn-secondary mt-6 inline-flex">
        {cta}
      </Link>
    </div>
  );
}

function SetupRow({
  title,
  body,
  cta,
  ctaHref,
}: {
  title: string;
  body: string;
  cta: string;
  ctaHref: string;
}) {
  return (
    <li className="py-6 flex items-center gap-8">
      <div className="flex-1">
        <p className="text-card-heading text-ink mb-1">{title}</p>
        <p className="text-caption text-body-muted">{body}</p>
      </div>
      <Link to={ctaHref} className="btn-pill-outline shrink-0">
        {cta}
      </Link>
    </li>
  );
}
