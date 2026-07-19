import { useAuthStore } from "../stores/auth";

const API_BASE = "http://127.0.0.1:18234";

export async function apiFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const { token, refreshToken, setAccessToken, logout } =
    useAuthStore.getState();

  const headers = new Headers(options.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  // Auto-refresh on 401
  if (res.status === 401 && refreshToken) {
    const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (refreshRes.ok) {
      const data = await refreshRes.json();
      // Just rotate the access token; keep the user we already have.
      setAccessToken(data.access_token, data.refresh_token);

      // Retry original request with new token
      headers.set("Authorization", `Bearer ${data.access_token}`);
      res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    } else {
      logout();
      window.location.href = "/login";
    }
  }

  return res;
}