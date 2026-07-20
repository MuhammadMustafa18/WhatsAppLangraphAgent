import { Outlet, Link, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";

const nav = [
  { to: "/", label: "Dashboard" },
  { to: "/providers", label: "Providers" },
  { to: "/personas", label: "Personas" },
  { to: "/connections", label: "Connections" },
  { to: "/chat", label: "Chat" },
  { to: "/observability", label: "Observability" },
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
    <div className="min-h-screen bg-canvas text-ink flex flex-col">
      {/* Announcement bar — full-width black strip with microcopy */}
      <div className="h-9 bg-cohere-black text-on-dark flex items-center justify-center px-lg shrink-0">
        <span className="text-micro">
          Alpha build · expect rough edges.{" "}
          <a
            href="https://github.com/MuhammadMustafa18/WhatsAppLangraphAgent"
            target="_blank"
            rel="noreferrer"
            className="underline underline-offset-2 hover:text-white"
          >
            View source
          </a>
        </span>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Left sidebar */}
        <aside className="w-60 border-r border-hairline bg-canvas flex flex-col shrink-0">
          {/* Logo */}
          <div className="px-6 pt-6 pb-8">
            <Link
              to="/"
              className="font-display text-card-heading tracking-tight text-ink"
            >
              WhatsApp Bot
            </Link>
          </div>

          {/* Nav links */}
          <nav className="flex-1 px-3">
            {nav.map((item) => {
              const active =
                item.to === "/"
                  ? location.pathname === "/"
                  : location.pathname.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`block px-3 py-2 text-body rounded-xs transition ${
                    active
                      ? "bg-soft-stone text-ink font-medium"
                      : "text-muted hover:bg-soft-stone/60 hover:text-ink"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* User identity + sign-out */}
          <div className="p-4 border-t border-hairline">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-8 h-8 rounded-full bg-soft-stone text-ink flex items-center justify-center text-caption font-medium uppercase shrink-0">
                {user?.username?.[0] ?? "?"}
              </div>
              <span
                className="text-caption text-ink max-w-[120px] truncate"
                title={user?.username ?? ""}
              >
                {user?.username ?? "(unknown)"}
              </span>
            </div>
            <button onClick={handleLogout} className="btn-pill-outline w-full">
              Sign out
            </button>
          </div>
        </aside>

        {/* Main content — generous section padding per Cohere whitespace philosophy */}
        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-[1100px] px-lg py-section">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
