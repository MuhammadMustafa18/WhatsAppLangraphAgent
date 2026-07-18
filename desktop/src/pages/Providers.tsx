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
          base_url: form.type === "custom" ? form.base_url || null : null,
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
          base_url: form.type === "custom" ? form.base_url || null : null,
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
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Providers</h1>
        <button
          onClick={openCreate}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
        >
          Add Provider
        </button>
      </div>

      {savedPlainKey && (
        <div className="bg-yellow-500/20 border border-yellow-500 text-yellow-200 p-4 rounded mb-4">
          <div className="flex items-start justify-between">
            <div>
              <p className="font-bold mb-1">
                Save this API key now — it won't be shown again.
              </p>
              <p className="font-mono text-sm break-all">
                {savedPlainKey.api_key_plain}
              </p>
            </div>
            <button
              onClick={() => setSavedPlainKey(null)}
              className="text-yellow-200 hover:text-white ml-4"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-500/20 border border-red-500 text-red-300 p-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {validationResult && (
        <div
          className={`p-3 rounded mb-4 text-sm border ${
            validationResult.valid
              ? "bg-green-500/20 border-green-500 text-green-200"
              : "bg-red-500/20 border-red-500 text-red-200"
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
        <div className="text-gray-400">Loading...</div>
      ) : providers.length === 0 ? (
        <div className="bg-gray-800 p-8 rounded-lg text-center">
          <p className="text-gray-400 mb-4">
            No providers configured yet. Add your first LLM provider to start
            chatting.
          </p>
          <button
            onClick={openCreate}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
          >
            Add Provider
          </button>
        </div>
      ) : (
        <div className="grid gap-3">
          {providers.map((p) => (
            <div key={p.id} className="bg-gray-800 p-4 rounded-lg">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-lg font-bold">{p.name}</h3>
                    {p.is_default && (
                      <span className="bg-blue-600 text-white text-xs px-2 py-0.5 rounded">
                        DEFAULT
                      </span>
                    )}
                  </div>
                  <p className="text-gray-400 text-sm">
                    {p.type} · {p.model}
                    {p.base_url && ` · ${p.base_url}`}
                  </p>
                  <p className="text-gray-500 text-xs mt-1">
                    Key: <span className="font-mono">{p.api_key_masked}</span> ·
                    Max tokens: {p.max_tokens}
                  </p>
                </div>
                <div className="flex gap-2">
                  {!p.is_default && (
                    <button
                      onClick={() => handleSetDefault(p)}
                      className="text-sm bg-gray-700 hover:bg-gray-600 text-gray-200 px-3 py-1 rounded"
                    >
                      Set Default
                    </button>
                  )}
                  <button
                    onClick={() => handleValidate(p)}
                    disabled={validatingId === p.id}
                    className="text-sm bg-gray-700 hover:bg-gray-600 text-gray-200 px-3 py-1 rounded disabled:opacity-50"
                  >
                    {validatingId === p.id ? "Checking..." : "Validate"}
                  </button>
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
          title={mode.kind === "create" ? "Add Provider" : `Edit ${mode.provider.name}`}
          onClose={closeModal}
        >
          <form onSubmit={handleSubmit}>
            <div className="mb-3">
              <label className="block text-gray-400 text-sm mb-1">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
                maxLength={100}
              />
            </div>

            <div className="mb-3">
              <label className="block text-gray-400 text-sm mb-1">Type</label>
              <select
                value={form.type}
                onChange={(e) =>
                  setForm({ ...form, type: e.target.value as ProviderType })
                }
                className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {PROVIDER_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>

            {form.type === "custom" && (
              <div className="mb-3">
                <label className="block text-gray-400 text-sm mb-1">
                  Base URL
                </label>
                <input
                  type="text"
                  value={form.base_url}
                  onChange={(e) =>
                    setForm({ ...form, base_url: e.target.value })
                  }
                  placeholder="http://localhost:11434/v1"
                  className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>
            )}

            <div className="mb-3">
              <label className="block text-gray-400 text-sm mb-1">
                API Key {mode.kind === "edit" && (
                  <span className="text-gray-500">
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
                className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                required={mode.kind === "create"}
                autoComplete="off"
              />
            </div>

            <div className="mb-3">
              <label className="block text-gray-400 text-sm mb-1">Model</label>
              <input
                type="text"
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
                placeholder="gpt-4o"
                className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
                maxLength={100}
              />
            </div>

            <div className="mb-4">
              <label className="block text-gray-400 text-sm mb-1">
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
                className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
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