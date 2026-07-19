import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./stores/auth";
import Layout from "./components/Layout";
import LoadingScreen from "./components/LoadingScreen";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Providers from "./pages/Providers";
import Personas from "./pages/Personas";
import Connections from "./pages/Connections";
import Chat from "./pages/Chat";

const BACKEND_URL = "http://127.0.0.1:18234";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let retries = 0;

    const start = Date.now();

    function poll() {
      fetch(`${BACKEND_URL}/health`)
        .then((r) => {
          if (r.ok && !cancelled) {
            const elapsed = Date.now() - start;
            const remaining = 1500 - elapsed;
            if (remaining > 0) {
              setTimeout(() => setReady(true), remaining);
            } else {
              setReady(true);
            }
          }
        })
        .catch(() => {
          if (!cancelled && retries < 120) {
            retries++;
            setTimeout(poll, 1000);
          }
        });
    }

    poll();
    return () => { cancelled = true; };
  }, []);

  if (!ready) return <LoadingScreen />;

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
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
