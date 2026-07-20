import { useEffect, useState } from "react";
import Modal from "../components/Modal";
import {
  createProvider,
  deleteProvider,
  listProviders,
  ProviderCreate,
  ProviderCreateResponse,
  ProviderResponse,
  ProviderType,
  ProviderUpdate,
  setDefaultProvider,
  updateProvider,
  validateProvider,
} from "../api/providers";

interface ProviderPreset {
  label: string;
  name: string;
  type: ProviderType;
  base_url: string;
  model: string;
  max_tokens: number;
}

const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    label: "GPT-4o",
    name: "gpt",
    type: "openai",
    base_url: "",
    model: "gpt-4o",
    max_tokens: 4096,
  },
  {
    label: "GPT-4o Mini",
    name: "gpt",
    type: "openai",
    base_url: "",
    model: "gpt-4o-mini",
    max_tokens: 8192,
  },
  {
    label: "Claude",
    name: "claude",
    type: "anthropic",
    base_url: "",
    model: "claude-sonnet-4-5",
    max_tokens: 4096,
  },
  {
    label: "LM Studio",
    name: "local",
    type: "custom",
    base_url: "http://localhost:1234/v1",
    model: "auto",
    max_tokens: 4096,
  },
  {
    label: "Ollama",
    name: "local",
    type: "custom",
    base_url: "http://localhost:11434/v1",
    model: "llama3",
    max_tokens: 4096,
  },
  {
    label: "Groq",
    name: "groq",
    type: "openai",
    base_url: "https://api.groq.com/openai/v1",
    model: "llama3-70b-8192",
    max_tokens: 4096,
  },
];

type FormMode =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; provider: ProviderResponse };

const PROVIDER_TYPES: ProviderType[] = ["openai", "anthropic", "custom"];

interface FormState {
  name: string;
  type: ProviderType;
  base_url: string;
  api_key: string;
  model: string;
  max_tokens: number;
}

const EMPTY_FORM: FormState = {
  name: "",
  type: "openai",
  base_url: "",
  api_key: "",
  model: "",
  max_tokens: 1024,
};

function providerToForm(p: ProviderResponse): FormState {
  return {
    name: p.name,
    type: p.type,
    base_url: p.base_url ?? "",
    api_key: "", // never pre-fill; force re-entry on edit
    model: p.model,
    max_tokens: p.max_tokens,
  };
}

export default function Providers() {
  const [providers, setProviders] = useState<ProviderResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<FormMode>({ kind: "closed" });
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [savedPlainKey, setSavedPlainKey] = useState<ProviderCreateResponse | null>(
    null
  );
  const [validatingId, setValidatingId] = useState<string | null>(null);
  const [validationResult, setValidationResult] = useState<{
    id: string;
    valid: boolean;
  } | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const list = await listProviders();
      setProviders(list);
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

  function openEdit(p: ProviderResponse) {
    setForm(providerToForm(p));
    setMode({ kind: "edit", provider: p });
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
        const data: ProviderCreate = {
          name: form.name,
          type: form.type,
          base_url: form.base_url || null,
          api_key: form.api_key,
          model: form.model,
          max_tokens: form.max_tokens,
        };
        const created = await createProvider(data);
        setSavedPlainKey(created);
        await refresh();
        closeModal();
      } else if (mode.kind === "edit") {
        const data: ProviderUpdate = {
          name: form.name,
          type: form.type,
          base_url: form.base_url || null,
          model: form.model,
          max_tokens: form.max_tokens,
        };
        if (form.api_key) {
          data.api_key = form.api_key;
        }
        await updateProvider(mode.provider.id, data);
        await refresh();
        closeModal();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(p: ProviderResponse) {
    if (!confirm(`Delete provider "${p.name}"? This cannot be undone.`)) return;
    try {
      await deleteProvider(p.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleValidate(p: ProviderResponse) {
    setValidatingId(p.id);
    setValidationResult(null);
    try {
      const valid = await validateProvider(p.id);
      setValidationResult({ id: p.id, valid });
    } catch (e) {
      setValidationResult({
        id: p.id,
        valid: false,
      });
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setValidatingId(null);
    }
  }

  async function handleSetDefault(p: ProviderResponse) {
    try {
      await setDefaultProvider(p.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-section flex items-end justify-between gap-8">
        <div>
          <p className="mono-label text-muted mb-3">Models</p>
          <h1 className="font-display text-section-heading text-ink">
            Providers
          </h1>
          <p className="text-body-large text-body-muted max-w-xl mt-3">
            LLM backends the bot can call. Mark one as default for new sessions.
          </p>
        </div>
        <button onClick={openCreate} className="btn-primary shrink-0">
          Add provider
        </button>
      </div>

      {savedPlainKey && (
        <div className="mb-8 border border-coral/40 bg-coral/10 text-ink px-6 py-4 rounded-sm">
          <div className="flex items-start justify-between gap-6">
            <div>
              <p className="font-medium mb-2">
                Save this API key now — it won't be shown again.
              </p>
              <p className="font-mono text-mono-label text-ink break-all bg-canvas border border-card-border px-3 py-2 rounded-xs">
                {savedPlainKey.api_key_plain}
              </p>
            </div>
            <button
              onClick={() => setSavedPlainKey(null)}
              className="btn-secondary shrink-0"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-8 border border-error/30 bg-error/5 text-error px-4 py-3 text-caption rounded-sm">
          {error}
        </div>
      )}

      {validationResult && (
        <div
          className={`mb-8 px-4 py-3 text-caption border rounded-sm ${
            validationResult.valid
              ? "border-deep-green/30 bg-pale-green text-ink"
              : "border-error/30 bg-error/5 text-error"
          }`}
        >
          {validationResult.valid
            ? "✓ Provider key is valid"
            : "✗ Provider key failed validation"}
          <button
            onClick={() => setValidationResult(null)}
            className="float-right opacity-70 hover:opacity-100"
          >
            ×
          </button>
        </div>
      )}

      {loading ? (
        <p className="text-body-muted">Loading…</p>
      ) : providers.length === 0 ? (
        <section className="product-card text-center">
          <p className="text-body-large text-ink mb-6 max-w-md mx-auto">
            No providers configured yet. Add your first LLM provider to start
            chatting.
          </p>
          <button onClick={openCreate} className="btn-primary">
            Add provider
          </button>
        </section>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {providers.map((p) => (
            <article key={p.id} className="product-card flex flex-col">
              <div className="flex items-start justify-between gap-3 mb-2">
                <h3 className="font-display text-feature-heading text-ink">
                  {p.name}
                </h3>
                {p.is_default && (
                  <span className="mono-label bg-primary text-on-dark px-2 py-0.5 rounded-xs shrink-0">
                    Default
                  </span>
                )}
              </div>
              <p className="mono-label text-muted mb-4">
                {p.type} · {p.model}
                {p.base_url && ` · ${p.base_url}`}
              </p>
              <hr className="mb-4" />
              <p className="text-caption text-body-muted mb-6">
                <span className="font-mono">{p.api_key_masked}</span> · max{" "}
                {p.max_tokens.toLocaleString()} tokens
              </p>
              <div className="mt-auto flex flex-wrap gap-2">
                {!p.is_default && (
                  <button
                    onClick={() => handleSetDefault(p)}
                    className="btn-pill-outline"
                  >
                    Set default
                  </button>
                )}
                <button
                  onClick={() => handleValidate(p)}
                  disabled={validatingId === p.id}
                  className="btn-pill-outline disabled:opacity-50"
                >
                  {validatingId === p.id ? "Checking…" : "Validate"}
                </button>
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
          title={mode.kind === "create" ? "Add Provider" : `Edit ${mode.provider.name}`}
          onClose={closeModal}
          maxWidth="max-w-3xl"
        >
          <form onSubmit={handleSubmit}>
            {mode.kind === "create" && (
              <div className="mb-5">
                <p className="text-caption text-ink mb-2">Quick-start presets</p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setForm(EMPTY_FORM)}
                    className={`px-3 py-1.5 text-micro font-medium rounded-xs border transition ${
                      form.name === "" && form.model === ""
                        ? "bg-ink text-white border-ink"
                        : "bg-canvas text-muted border-hairline hover:text-ink hover:border-ink/30"
                    }`}
                  >
                    Custom
                  </button>
                  {PROVIDER_PRESETS.map((p) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() =>
                        setForm({
                          name: p.name,
                          type: p.type,
                          base_url: p.base_url,
                          api_key: "",
                          model: p.model,
                          max_tokens: p.max_tokens,
                        })
                      }
                      className={`px-3 py-1.5 text-micro font-medium rounded-xs border transition ${
                        form.name === p.name && form.model === p.model
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

            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-caption text-ink mb-2">Name</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus"
                  required
                  maxLength={100}
                />
              </div>
              <div>
                <label className="block text-caption text-ink mb-2">Type</label>
                <select
                  value={form.type}
                  onChange={(e) =>
                    setForm({ ...form, type: e.target.value as ProviderType })
                  }
                  className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus"
                >
                  {PROVIDER_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="mb-4">
              <label className="block text-caption text-ink mb-2">
                Base URL
                <span className="text-body-muted">
                  {" "}
                  (leave blank to use provider default)
                </span>
              </label>
              <input
                type="text"
                value={form.base_url}
                onChange={(e) =>
                  setForm({ ...form, base_url: e.target.value })
                }
                placeholder={form.type === "openai" ? "https://api.openai.com/v1" : form.type === "anthropic" ? "https://api.anthropic.com" : "http://localhost:11434/v1"}
                className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus"
              />
            </div>

            <div className="mb-4">
              <label className="block text-caption text-ink mb-2">
                API Key{" "}
                {mode.kind === "edit" && (
                  <span className="text-body-muted">
                    (leave blank to keep current)
                  </span>
                )}
              </label>
              <input
                type="password"
                value={form.api_key}
                onChange={(e) =>
                  setForm({ ...form, api_key: e.target.value })
                }
                className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus"
                required={mode.kind === "create"}
                autoComplete="off"
              />
            </div>

            <div className="grid grid-cols-2 gap-4 mb-6">
              <div>
                <label className="block text-caption text-ink mb-2">Model</label>
                <input
                  type="text"
                  value={form.model}
                  onChange={(e) => setForm({ ...form, model: e.target.value })}
                  placeholder="gpt-4o"
                  className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus"
                  required
                  maxLength={100}
                />
              </div>
              <div>
                <label className="block text-caption text-ink mb-2">
                  Max tokens
                </label>
                <input
                  type="number"
                  value={form.max_tokens}
                  onChange={(e) =>
                    setForm({ ...form, max_tokens: parseInt(e.target.value) || 1024 })
                  }
                  min={1}
                  max={32000}
                  className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus"
                />
              </div>
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