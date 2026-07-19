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
    <div className="min-h-screen bg-gray-900 flex items-center justify-center">
      <div className="bg-gray-800 p-8 rounded-lg w-96">
        <h1 className="text-2xl font-bold mb-6 text-center">
          {isRegister ? "Register" : "Login"}
        </h1>

        {error && (
          <div className="bg-red-500/20 text-red-400 p-3 rounded mb-4 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-gray-400 text-sm mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
              disabled={submitting}
              autoComplete="username"
            />
          </div>

          <div className="mb-6">
            <label className="block text-gray-400 text-sm mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-gray-700 text-white px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
              disabled={submitting}
              autoComplete={isRegister ? "new-password" : "current-password"}
              minLength={6}
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded font-medium disabled:opacity-50"
          >
            {submitting ? "Working..." : isRegister ? "Register" : "Login"}
          </button>
        </form>

        <p className="text-gray-400 text-sm text-center mt-4">
          {isRegister ? "Already have an account?" : "Don't have an account?"}{" "}
          <button
            onClick={() => {
              setIsRegister(!isRegister);
              setError("");
            }}
            className="text-blue-400 hover:underline"
            disabled={submitting}
          >
            {isRegister ? "Login" : "Register"}
          </button>
        </p>
      </div>
    </div>
  );
}