import { Outlet, Link, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";

const nav = [
  { to: "/", label: "Dashboard" },
  { to: "/providers", label: "Providers" },
  { to: "/personas", label: "Personas" },
  { to: "/connections", label: "Connections" },
  { to: "/chat", label: "Chat" },
];

export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex h-screen bg-gray-900 text-white">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-800 flex flex-col">
        <div className="p-4 text-lg font-bold border-b border-gray-700">
          WhatsApp Bot
        </div>
        <nav className="flex-1 p-2">
          {nav.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`block px-3 py-2 rounded mb-1 ${
                location.pathname === item.to
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:bg-gray-700 hover:text-white"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        {/* User identity + logout — always visible when authenticated.
            App.tsx's ProtectedRoute guarantees a token exists by the time
            Layout renders. */}
        <div className="p-3 border-t border-gray-700">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-sm font-bold uppercase">
              {user?.username?.[0] ?? "?"}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs text-gray-500">Logged in as</div>
              <div
                className="text-sm font-medium truncate"
                title={user?.username ?? ""}
              >
                {user?.username ?? "(unknown)"}
              </div>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full px-3 py-2 text-left text-gray-400 hover:bg-gray-700 hover:text-white rounded text-sm"
          >
            Logout
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}