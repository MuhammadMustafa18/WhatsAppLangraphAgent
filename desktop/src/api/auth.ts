// Typed wrapper around apiFetch for /auth endpoints.

import { apiFetch } from "./client";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface MeResponse {
  id: string;
  username: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
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

export async function register(data: RegisterRequest): Promise<TokenResponse> {
  const res = await apiFetch("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJson<TokenResponse>(res);
}

export async function login(data: LoginRequest): Promise<TokenResponse> {
  const res = await apiFetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJson<TokenResponse>(res);
}

export async function refresh(refreshToken: string): Promise<TokenResponse> {
  const res = await apiFetch("/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  return readJson<TokenResponse>(res);
}

export async function me(): Promise<MeResponse> {
  const res = await apiFetch("/auth/me");
  return readJson<MeResponse>(res);
}