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
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Personas</h1>
          <p className="text-gray-400 text-sm mt-1">
            How your bot answers. Each persona is a system prompt + optional
            knowledge base + optional model pin.
          </p>
        </div>
        <button
          onClick={openCreate}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
        >
          Add Persona
        </button>
      </div>

      {error && (
        <div className="bg-red-500/20 border border-red-500 text-red-300 p-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : personas.length === 0 ? (
        <div className="bg-gray-800 p-8 rounded-lg text-center">
          <p className="text-gray-400 mb-4">
            No personas yet. Create one — start with a name and a system prompt
            that tells the bot how to behave.
          </p>
          <button
            onClick={openCreate}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
          >
            Add Persona
          </button>
        </div>
      ) : (
        <div className="grid gap-3">
          {personas.map((p) => (
            <div key={p.id} className="bg-gray-800 p-4 rounded-lg">
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-lg font-bold">{p.name}</h3>
                    {p.is_active ? (
                      <span className="bg-green-600 text-white text-xs px-2 py-0.5 rounded">
                        ACTIVE
                      </span>
                    ) : (
                      <span className="bg-gray-600 text-white text-xs px-2 py-0.5 rounded">
                        INACTIVE
                      </span>
                    )}
                  </div>
                  <p className="text-gray-300 text-sm whitespace-pre-wrap break-words mb-2">
                    {p.system_prompt}
                  </p>
                  {p.knowledge_base && (
                    <details className="mb-2">
                      <summary className="text-gray-400 text-xs cursor-pointer">
                        Knowledge base
                      </summary>
                      <p className="text-gray-400 text-xs mt-1 whitespace-pre-wrap break-words">
                        {p.knowledge_base}
                      </p>
                    </details>
                  )}
                  <p className="text-gray-500 text-xs">
                    Model: <span className="font-mono">{providerName(p.model_override)}</span>
                  </p>
                </div>
                <div className="flex gap-2 ml-4">
                  <button
                    onClick={() => openEdit(p)}
                    className="text-sm bg-gray-700 hover:bg-gray-600 text-gray-200 px-3 py-1 rounded"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(p)}
                    className="text-sm bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
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
            <div className="mb-3">
              <label className="block text-gray-400 text-sm mb-1">
                Name
                <span className="text-gray-500 text-xs ml-2">
                  (use lowercase: resume, services, booking, etc.)
                </span>
              </label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
                maxLength={100}
                placeholder="support"
              />
            </div>

            <div className="mb-3">
              <label className="block text-gray-400 text-sm mb-1">
                System prompt
                <span className="text-gray-500 text-xs ml-2">
                  (who the bot is, how it talks, what to focus on)
                </span>
              </label>
              <textarea
                value={form.system_prompt}
                onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                required
                rows={6}
                placeholder="You are a support agent for a small ecommerce store. Be brief, friendly, and always ask for the order number before looking anything up."
              />
            </div>

            <div className="mb-3">
              <label className="block text-gray-400 text-sm mb-1">
                Knowledge base
                <span className="text-gray-500 text-xs ml-2">
                  (optional reference text, appended to the system prompt)
                </span>
              </label>
              <textarea
                value={form.knowledge_base}
                onChange={(e) => setForm({ ...form, knowledge_base: e.target.value })}
                className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                rows={4}
                placeholder="FAQ: returns within 30 days. Shipping is free over $50. Customer support hours are 9am-5pm EST."
              />
            </div>

            <div className="mb-3">
              <label className="block text-gray-400 text-sm mb-1">
                Model override
                <span className="text-gray-500 text-xs ml-2">
                  (optional — leave blank to use your default provider)
                </span>
              </label>
              <select
                value={form.model_override}
                onChange={(e) => setForm({ ...form, model_override: e.target.value })}
                className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">— Default provider —</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.model})
                  </option>
                ))}
              </select>
              {providers.length === 0 && (
                <p className="text-gray-500 text-xs mt-1">
                  No providers configured yet.{" "}
                  <a href="/providers" className="text-blue-400 hover:underline">
                    Add one first.
                  </a>
                </p>
              )}
            </div>

            <div className="mb-4">
              <label className="flex items-center gap-2 text-gray-400 text-sm">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                  className="rounded"
                />
                Active (inactive personas are ignored by the bot)
              </label>
            </div>

            {error && (
              <div className="bg-red-500/20 text-red-300 p-2 rounded mb-3 text-sm">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={closeModal}
                className="px-4 py-2 rounded text-gray-300 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded disabled:opacity-50"
              >
                {submitting
                  ? "Saving..."
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