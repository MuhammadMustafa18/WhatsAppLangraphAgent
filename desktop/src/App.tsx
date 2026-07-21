import { useCallback, useEffect, useRef, useState } from "react";
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
import {
  SIDECARS,
  waitForHealthy,
  listenForSidecarErrors,
  type SidecarId,
  type SidecarErrorPayload,
} from "./lib/health";

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
  const [serviceErrors, setServiceErrors] = useState<
    Record<SidecarId, string | null>
  >({
    backend: null,
    baileys: null,
  });
  const [retryKey, setRetryKey] = useState(0);
  // Use a ref for the Tauri event unlistener so we don't lose it across
  // effect re-runs (stale closure hazard with async promise resolution).
  const unlistenRef = useRef<(() => void) | undefined>(undefined);
  // Track which services actually reported healthy (via ref, not state,
  // so async callbacks always see the latest value).
  const healthyRef = useRef<Record<SidecarId, boolean>>({
    backend: false,
    baileys: false,
  });

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    setReady(false);
    setError(null);
    setServiceErrors({ backend: null, baileys: null });
    setStatuses({ backend: "pending", baileys: "pending" });
    healthyRef.current = { backend: false, baileys: false };

    const start = Date.now();

    // ── Listen for sidecar-error events from the Tauri Rust process ──
    listenForSidecarErrors((payload: SidecarErrorPayload) => {
      if (signal.aborted) return;
      const { id, error: errMsg } = payload;
      setServiceErrors((prev) => (prev[id] ? prev : { ...prev, [id]: errMsg }));
      setStatuses((prev) =>
        prev[id] === "error" ? prev : { ...prev, [id]: "error" },
      );
      setError("Some services failed to start. See details below.");
    }).then((unsub) => {
      unlistenRef.current = unsub;
    });

    // ── Transition to the app once the backend is healthy ──
    // (baileys/WhatsApp is optional — the app works without it).
    function transitionIfReady() {
      if (signal.aborted) return;
      if (healthyRef.current.backend) {
        const remaining = MIN_DISPLAY_MS - (Date.now() - start);
        setTimeout(() => {
          if (!signal.aborted) setReady(true);
        }, Math.max(0, remaining));
      }
    }

    // ── Poll health endpoints ──
    const pollOne = (id: SidecarId) =>
      waitForHealthy("", signal, id, STARTUP_TIMEOUT_MS)
        .then(() => {
          if (signal.aborted) return;
          healthyRef.current[id] = true;
          setStatuses((prev) =>
            prev[id] === "ok" ? prev : { ...prev, [id]: "ok" },
          );
          transitionIfReady();
        })
        .catch((err) => {
          if (signal.aborted || err?.message === "aborted") return;
          // Only mark as error if we haven't already received a specific
          // error from the sidecar event channel (which is more informative).
          setStatuses((prev) =>
            prev[id] === "error" ? prev : { ...prev, [id]: "error" },
          );
          setServiceErrors((prev) =>
            prev[id]
              ? prev
              : {
                  ...prev,
                  [id]:
                    "Timed out waiting for service. Make sure the app is installed correctly and no other program is using the required ports.",
                },
          );
          setError("Some services failed to start. See details below.");
        });

    // Start polling both services in parallel (no forced transition on settle).
    Promise.allSettled(
      (Object.keys(SIDECARS) as SidecarId[]).map((id) => pollOne(id)),
    );

    return () => {
      controller.abort();
      unlistenRef.current?.();
      unlistenRef.current = undefined;
    };
  }, [retryKey]);

  const handleRetry = useCallback(() => {
    setRetryKey((k) => k + 1);
  }, []);

  if (!ready) {
    return (
      <LoadingScreen
        services={{
          backend: { label: SIDECARS.backend.label, status: statuses.backend },
          baileys: { label: SIDECARS.baileys.label, status: statuses.baileys },
        }}
        serviceErrors={serviceErrors}
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
