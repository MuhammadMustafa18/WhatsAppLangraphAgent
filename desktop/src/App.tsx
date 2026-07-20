import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./stores/auth";
import Layout from "./components/Layout";
import LoadingScreen, { type SidecarStatus } from "./components/LoadingScreen";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Providers from "./pages/Providers";
import Personas from "./pages/Personas";
import Connections from "./pages/Connections";
import Chat from "./pages/Chat";
import Observability from "./pages/Observability";
import { SIDECARS, waitForHealthy, type SidecarId } from "./lib/health";

// Anti-flash: keep the splash visible for at least this long even if both
// sidecars come up instantly, so we never show a jarring flash.
const MIN_DISPLAY_MS = 1500;
// Hard ceiling per sidecar. If both sidecars don't report healthy in this
// window we surface an error instead of spinning forever.
const STARTUP_TIMEOUT_MS = 60_000;

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statuses, setStatuses] = useState<Record<SidecarId, SidecarStatus>>({
    backend: "pending",
    baileys: "pending",
  });
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    setReady(false);
    setError(null);
    setStatuses({ backend: "pending", baileys: "pending" });

    const start = Date.now();

    const pollOne = (id: SidecarId) =>
      waitForHealthy(SIDECARS[id].url, signal, STARTUP_TIMEOUT_MS)
        .then(() => {
          if (!signal.aborted) {
            setStatuses((prev) =>
              prev[id] === "ok" ? prev : { ...prev, [id]: "ok" },
            );
          }
        })
        .catch((err) => {
          if (signal.aborted || err?.message === "aborted") return;
          setStatuses((prev) =>
            prev[id] === "error" ? prev : { ...prev, [id]: "error" },
          );
          setError(
            "Services didn't come up in time. Check that no other app is using the required ports and try again.",
          );
        });

    Promise.all(
      (Object.keys(SIDECARS) as SidecarId[]).map((id) => pollOne(id)),
    ).then(() => {
      if (signal.aborted) return;
      const remaining = MIN_DISPLAY_MS - (Date.now() - start);
      setTimeout(() => {
        if (!signal.aborted) setReady(true);
      }, Math.max(0, remaining));
    });

    return () => controller.abort();
  }, [retryKey]);

  const handleRetry = useCallback(() => setRetryKey((k) => k + 1), []);

  if (!ready) {
    return (
      <LoadingScreen
        services={{
          backend: { label: SIDECARS.backend.label, status: statuses.backend },
          baileys: { label: SIDECARS.baileys.label, status: statuses.baileys },
        }}
        error={error}
        onRetry={error ? handleRetry : undefined}
      />
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="providers" element={<Providers />} />
          <Route path="personas" element={<Personas />} />
          <Route path="connections" element={<Connections />} />
          <Route path="chat" element={<Chat />} />
          <Route path="observability" element={<Observability />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
