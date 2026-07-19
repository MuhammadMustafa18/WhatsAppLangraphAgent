import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { login, me, register } from "../api/auth";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const setTokens = useAuthStore((s) => s.setTokens);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      // 1. Register or login → tokens.
      const tokens = isRegister
        ? await register({ username, password })
        : await login({ username, password });

      // 2. Persist tokens (no user yet — that comes from /auth/me).
      setTokens(tokens.access_token, tokens.refresh_token, {
        id: "",
        username,
      });

      // 3. Fetch the real user (id + username) so the sidebar can show it.
      try {
        const me_ = await me();
        useAuthStore.getState().setUser({ id: me_.id, username: me_.username });
      } catch {
        // /auth/me failed but tokens are valid — fall back to what we have.
        // The sidebar will show the username we typed, which is fine.
      }

      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col">
      {/* Announcement bar — matches the authenticated nav so the brand reads
          continuously before and after login. */}
      <div className="h-9 bg-cohere-black text-on-dark flex items-center justify-center px-lg">
        <span className="text-micro">
          Alpha build · expect rough edges.
        </span>
      </div>

      <div className="flex-1 flex items-center justify-center px-lg">
        <div className="w-full max-w-[420px] text-center">
          {/* Tight display headline */}
          <h1 className="font-display text-section-heading text-ink mb-4">
            {isRegister ? "Create an account" : "Sign in"}
          </h1>
          <p className="text-body-large text-body-muted mb-12">
            {isRegister
              ? "Set up access to your WhatsApp command center."
              : "Welcome back. Continue where you left off."}
          </p>

          {error && (
            <div className="border border-error/30 bg-error/5 text-error px-4 py-3 mb-6 text-caption text-left rounded-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="text-left">
            <div className="mb-4">
              <label className="block text-caption text-ink mb-2">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus"
                required
                disabled={submitting}
                autoComplete="username"
              />
            </div>

            <div className="mb-8">
              <label className="block text-caption text-ink mb-2">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-canvas border border-border-light text-ink px-4 py-3 rounded-sm focus:outline-none focus:border-form-focus"
                required
                disabled={submitting}
                autoComplete={isRegister ? "new-password" : "current-password"}
                minLength={6}
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="btn-primary w-full"
            >
              {submitting
                ? "Working…"
                : isRegister
                ? "Create account"
                : "Sign in"}
            </button>
          </form>

          <p className="text-caption text-body-muted mt-8">
            {isRegister
              ? "Already have an account?"
              : "Don't have an account?"}{" "}
            <button
              onClick={() => {
                setIsRegister(!isRegister);
                setError("");
              }}
              className="btn-secondary"
              disabled={submitting}
            >
              {isRegister ? "Sign in" : "Create one"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
