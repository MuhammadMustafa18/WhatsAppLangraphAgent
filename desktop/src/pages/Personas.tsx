// Persona management page. Mirrors Providers.tsx in shape but is simpler:
// no secrets, no validate endpoint, no set-default flow. Personas have:
//   - name (unique per user)
//   - system_prompt (required)
//   - knowledge_base (optional)
//   - model_override (optional — picks which Provider this persona uses)
//   - is_active (toggle on/off)
//
// The model_override dropdown fetches /providers so the user can pin
// specific personas to specific LLM providers. None means "use the
// user's default provider at runtime" (the backend handles this).

import { useEffect, useState } from "react";
import Modal from "../components/Modal";
import {
  createPersona,
  deletePersona,
  listPersonas,
  PersonaCreate,
  PersonaResponse,
  PersonaUpdate,
  updatePersona,
} from "../api/personas";
import { listProviders, ProviderResponse } from "../api/providers";

interface Preset {
  label: string;
  name: string;
  system_prompt: string;
  knowledge_base: string;
}

const PRESETS: Preset[] = [
  {
    label: "Support",
    name: "support",
    system_prompt:
      "You are a support agent for a small ecommerce store. Be brief, friendly, and always ask for the order number before looking anything up.",
    knowledge_base:
      "FAQ: returns within 30 days. Shipping is free over $50. Customer support hours are 9am-5pm EST.",
  },
  {
    label: "Booking",
    name: "booking",
    system_prompt:
      "You handle appointment bookings and rescheduling. Be concise, confirm availability, and always ask for the preferred date and time before proceeding.",
    knowledge_base:
      "Appointments are 30 min slots. Cancellations must be 24hr in advance. Same-day bookings are available if slots are open.",
  },
  {
    label: "Resume",
    name: "resume",
    system_prompt:
      "You are a career advisor helping refine resumes and cover letters. Give direct, actionable feedback. Focus on achievements over duties.",
    knowledge_base: "",
  },
  {
    label: "Personal",
    name: "personal",
    system_prompt:
      "You are a friendly personal assistant. You chat casually, help with everyday questions, and never give professional advice (legal, medical, financial).",
    knowledge_base: "",
  },
  {
    label: "Services",
    name: "services",
    system_prompt:
      "You represent a small services business. Describe what you offer, quote prices, and direct the user to book a consultation for custom work.",
    knowledge_base: "",
  },
];

type FormMode =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; persona: PersonaResponse };

interface FormState {
  name: string;
  system_prompt: string;
  knowledge_base: string;
  model_override: string; // "" = no override
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  name: "",
  system_prompt: "",
  knowledge_base: "",
  model_override: "",
  is_active: true,
};

function personaToForm(p: PersonaResponse): FormState {
  return {
    name: p.name,
    system_prompt: p.system_prompt,
    knowledge_base: p.knowledge_base ?? "",
    model_override: p.model_override ?? "",
    is_active: p.is_active,
  };
}

export default function Personas() {
  const [personas, setPersonas] = useState<PersonaResponse[]>([]);
  const [providers, setProviders] = useState<ProviderResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<FormMode>({ kind: "closed" });
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [p, prov] = await Promise.all([listPersonas(), listProviders()]);
      setPersonas(p);
      setProviders(prov);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function openCreate() {
    setForm(EMPTY_FORM);
    setMode({ kind: "create" });
  }

  function openEdit(p: PersonaResponse) {
    setForm(personaToForm(p));
    setMode({ kind: "edit", persona: p });
  }

  function closeModal() {
    setMode({ kind: "closed" });
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode.kind === "create") {
        const data: PersonaCreate = {
          name: form.name.trim(),
          system_prompt: form.system_prompt,
          knowledge_base: form.knowledge_base.trim() || null,
          model_override: form.model_override || null,
          is_active: form.is_active,
        };
        await createPersona(data);
        await refresh();
        closeModal();
      } else if (mode.kind === "edit") {
        const data: PersonaUpdate = {
          name: form.name.trim(),
          system_prompt: form.system_prompt,
          knowledge_base: form.knowledge_base.trim() || null,
          model_override: form.model_override || null,
          is_active: form.is_active,
        };
        await updatePersona(mode.persona.id, data);
        await refresh();
        closeModal();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(p: PersonaResponse) {
    if (!confirm(`Delete persona "${p.name}"? This cannot be undone.`)) return;
    try {
      await deletePersona(p.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function providerName(id: string | null): string {
    if (!id) return "default provider";
    const prov = providers.find((pr) => pr.id === id);
    return prov ? `${prov.name} (${prov.model})` : "unknown provider";
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-section flex items-end justify-between gap-8">
        <div>
          <p className="mono-label text-muted mb-3">Behavior</p>
          <h1 className="font-display text-section-heading text-ink">
            Personas
          </h1>
          <p className="text-body-large text-body-muted max-w-xl mt-3">
            How your bot answers. Each persona is a system prompt plus an
            optional knowledge base and optional model pin.
          </p>
        </div>
        <button onClick={openCreate} className="btn-primary shrink-0">
          Add persona
        </button>
      </div>

      {error && (
        <div className="mb-8 border border-error/30 bg-error/5 text-error px-4 py-3 text-caption rounded-sm">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-body-muted">Loading…</p>
      ) : personas.length === 0 ? (
        <section className="product-card text-center">
          <p className="text-body-large text-ink mb-6 max-w-md mx-auto">
            No personas yet. Create one — start with a name and a system
            prompt that tells the bot how to behave.
          </p>
          <button onClick={openCreate} className="btn-primary">
            Add persona
          </button>
        </section>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {personas.map((p) => (
            <article key={p.id} className="product-card flex flex-col">
              <div className="flex items-start justify-between gap-3 mb-3">
                <h3 className="font-display text-feature-heading text-ink">
                  {p.name}
                </h3>
                {p.is_active ? (
                  <span className="mono-label bg-deep-green text-on-dark px-2 py-0.5 rounded-xs shrink-0">
                    Active
                  </span>
                ) : (
                  <span className="mono-label bg-muted text-canvas px-2 py-0.5 rounded-xs shrink-0">
                    Inactive
                  </span>
                )}
              </div>
              <p className="text-body text-ink whitespace-pre-wrap break-words mb-4">
                {p.system_prompt}
              </p>
              {p.knowledge_base && (
                <details className="mb-4">
                  <summary className="mono-label text-muted cursor-pointer">
                    Knowledge base
                  </summary>
                  <p className="text-caption text-body-muted mt-2 whitespace-pre-wrap break-words">
                    {p.knowledge_base}
                  </p>
                </details>
              )}
              <hr className="mb-4" />
              <p className="text-caption text-body-muted mb-6">
                Model: <span className="font-mono">{providerName(p.model_override)}</span>
              </p>
              <div className="mt-auto flex gap-2">
                <button
                  onClick={() => openEdit(p)}
                  className="btn-pill-outline"
                >
                  Edit
                </button>
                <button
                  onClick={() => handleDelete(p)}
                  className="btn-pill-outline hover:border-error hover:text-error"
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      {mode.kind !== "closed" && (
        <Modal
          title={mode.kind === "create" ? "Add Persona" : `Edit ${mode.persona.name}`}
          onClose={closeModal}
          maxWidth="max-w-2xl"
        >
          <form onSubmit={handleSubmit}>
            {mode.kind === "create" && (
              <div className="mb-5">
                <p className="text-caption text-ink mb-2">Quick-start presets</p>
                <div className="flex flex-wrap gap-2">
                  {PRESETS.map((p) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() =>
                        setForm({
                          name: p.name,
                          system_prompt: p.system_prompt,
                          knowledge_base: p.knowledge_base,
                          model_override: "",
                          is_active: true,
                        })
                      }
                      className={`px-3 py-1.5 text-micro font-medium rounded-xs border transition ${
                        form.name === p.name && form.system_prompt === p.system_prompt
                          ? "bg-ink text-white border-ink"
                          : "bg-canvas text-muted border-hairline hover:text-ink hover:border-ink/30"
                      }`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mb-4">
              <label className="block text-caption text-ink mb-2">
                Name{" "}
                <span className="text-body-muted">
                  (lowercase: resume, services, booking…)
                </span>
              </label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus"
                required
                maxLength={100}
                placeholder="support"
              />
            </div>

            <div className="mb-4">
              <label className="block text-caption text-ink mb-2">
                System prompt{" "}
                <span className="text-body-muted">
                  (who the bot is, how it talks, what to focus on)
                </span>
              </label>
              <textarea
                value={form.system_prompt}
                onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus font-mono text-caption"
                required
                rows={6}
                placeholder="You are a support agent for a small ecommerce store. Be brief, friendly, and always ask for the order number before looking anything up."
              />
            </div>

            <div className="mb-4">
              <label className="block text-caption text-ink mb-2">
                Knowledge base{" "}
                <span className="text-body-muted">
                  (optional reference text, appended to the system prompt)
                </span>
              </label>
              <textarea
                value={form.knowledge_base}
                onChange={(e) => setForm({ ...form, knowledge_base: e.target.value })}
                className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus font-mono text-caption"
                rows={4}
                placeholder="FAQ: returns within 30 days. Shipping is free over $50. Customer support hours are 9am-5pm EST."
              />
            </div>

            <div className="mb-4">
              <label className="block text-caption text-ink mb-2">
                Model override{" "}
                <span className="text-body-muted">
                  (optional — leave blank to use your default provider)
                </span>
              </label>
              <select
                value={form.model_override}
                onChange={(e) => setForm({ ...form, model_override: e.target.value })}
                className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus"
              >
                <option value="">— Default provider —</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.model})
                  </option>
                ))}
              </select>
              {providers.length === 0 && (
                <p className="text-caption text-body-muted mt-2">
                  No providers configured yet.{" "}
                  <a href="/providers" className="btn-secondary inline-flex">
                    Add one first
                  </a>
                </p>
              )}
            </div>

            <div className="mb-6">
              <label className="flex items-center gap-3 text-caption text-ink">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                  className="rounded-xs border-border-light"
                />
                Active (inactive personas are ignored by the bot)
              </label>
            </div>

            {error && (
              <div className="mb-4 border border-error/30 bg-error/5 text-error px-3 py-2 text-caption rounded-sm">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={closeModal}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="btn-primary disabled:opacity-50"
              >
                {submitting
                  ? "Saving…"
                  : mode.kind === "create"
                    ? "Create"
                    : "Save"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}