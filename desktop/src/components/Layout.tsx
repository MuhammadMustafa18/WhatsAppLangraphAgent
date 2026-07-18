import { Outlet, Link, useLocation } from "react-router-dom";
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
  const logout = useAuthStore((s) => s.logout);

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
        <div className="p-2 border-t border-gray-700">
          <button
            onClick={logout}
            className="w-full px-3 py-2 text-left text-gray-400 hover:bg-gray-700 hover:text-white rounded"
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
