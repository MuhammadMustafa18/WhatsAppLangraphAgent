// Typed wrapper around apiFetch for the /providers endpoints.

import { apiFetch } from "./client";

export type ProviderType = "openai" | "anthropic" | "custom";

export interface ProviderResponse {
  id: string;
  name: string;
  type: ProviderType;
  base_url: string | null;
  api_key_masked: string;
  model: string;
  max_tokens: number;
  is_default: boolean;
  created_at: string;
}

export interface ProviderCreateResponse extends ProviderResponse {
  api_key_plain: string; // present only on POST response
}

export interface ProviderCreate {
  name: string;
  type: ProviderType;
  base_url?: string | null;
  api_key: string;
  model: string;
  max_tokens?: number;
}

export interface ProviderUpdate {
  name?: string;
  type?: ProviderType;
  base_url?: string | null;
  api_key?: string;
  model?: string;
  max_tokens?: number;
  is_default?: boolean;
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail ?? detail;
    } catch {
      // body wasn't JSON
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function listProviders(): Promise<ProviderResponse[]> {
  const res = await apiFetch("/providers");
  return readJson<ProviderResponse[]>(res);
}

export async function createProvider(
  data: ProviderCreate
): Promise<ProviderCreateResponse> {
  const res = await apiFetch("/providers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJson<ProviderCreateResponse>(res);
}

export async function updateProvider(
  id: string,
  data: ProviderUpdate
): Promise<ProviderResponse> {
  const res = await apiFetch(`/providers/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJson<ProviderResponse>(res);
}

export async function deleteProvider(id: string): Promise<void> {
  const res = await apiFetch(`/providers/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`HTTP ${res.status}`);
  }
}

export async function validateProvider(id: string): Promise<boolean> {
  const res = await apiFetch(`/providers/${id}/validate`, { method: "POST" });
  const data = await readJson<{ valid: boolean }>(res);
  return data.valid;
}

export async function setDefaultProvider(id: string): Promise<ProviderResponse> {
  const res = await apiFetch(`/providers/${id}/default`, { method: "POST" });
  return readJson<ProviderResponse>(res);
}