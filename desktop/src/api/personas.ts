// Typed wrapper around apiFetch for the /personas endpoints.

import { apiFetch } from "./client";

export interface PersonaResponse {
  id: string;
  name: string;
  system_prompt: string;
  knowledge_base: string | null;
  model_override: string | null;
  is_active: boolean;
  created_at: string;
}

export interface PersonaCreate {
  name: string;
  system_prompt: string;
  knowledge_base?: string | null;
  model_override?: string | null;
  is_active?: boolean;
}

export interface PersonaUpdate {
  name?: string;
  system_prompt?: string;
  knowledge_base?: string | null;
  model_override?: string | null;
  is_active?: boolean;
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

export async function listPersonas(): Promise<PersonaResponse[]> {
  const res = await apiFetch("/personas");
  return readJson<PersonaResponse[]>(res);
}

export async function createPersona(
  data: PersonaCreate
): Promise<PersonaResponse> {
  const res = await apiFetch("/personas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJson<PersonaResponse>(res);
}

export async function updatePersona(
  id: string,
  data: PersonaUpdate
): Promise<PersonaResponse> {
  const res = await apiFetch(`/personas/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJson<PersonaResponse>(res);
}

export async function deletePersona(id: string): Promise<void> {
  const res = await apiFetch(`/personas/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`HTTP ${res.status}`);
  }
}