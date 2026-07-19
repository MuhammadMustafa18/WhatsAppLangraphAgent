export default function Chat() {
  return (
    <div>
      {/* Header */}
      <div className="mb-section">
        <p className="mono-label text-muted mb-3">Preview</p>
        <h1 className="font-display text-section-heading text-ink">
          Chat
        </h1>
        <p className="text-body-large text-body-muted max-w-xl mt-3">
          Test your personas in a sandboxed conversation before pointing them at
          a live WhatsApp number.
        </p>
      </div>

      {/* Coming-soon dark band */}
      <section className="dark-band mb-section">
        <p className="mono-label text-on-dark/70 mb-3">Status</p>
        <h2 className="font-display text-card-heading text-on-dark mb-3">
          Coming soon.
        </h2>
        <p className="text-body-large text-on-dark/80 max-w-xl">
          The chat preview will let you pick a persona and provider, send a
          message, and watch the full request flow — including tool calls and
          persona switches — in real time.
        </p>
      </section>

      {/* Capability-card placeholder grid */}
      <section>
        <p className="mono-label text-muted mb-3">Planned capabilities</p>
        <ul className="grid gap-6 md:grid-cols-3">
          <CapabilityCard
            title="Persona switcher"
            body="Try each persona side-by-side without leaving the page."
          />
          <CapabilityCard
            title="Live trace"
            body="Inspect tool calls, retrieval, and the final prompt assembled for the model."
          />
          <CapabilityCard
            title="Cost preview"
            body="See token counts and per-message cost as you iterate on prompts."
          />
        </ul>
      </section>
    </div>
  );
}

function CapabilityCard({ title, body }: { title: string; body: string }) {
  return (
    <li className="bg-canvas border-t border-hairline pt-6">
      <h3 className="font-display text-feature-heading text-ink mb-3">
        {title}
      </h3>
      <p className="text-body text-body-muted">{body}</p>
    </li>
  );
}
