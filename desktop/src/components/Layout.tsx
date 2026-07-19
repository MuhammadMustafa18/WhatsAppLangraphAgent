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
    <div className="min-h-screen bg-canvas text-ink flex flex-col">
      {/* Announcement bar — Cohere's full-width black strip with microcopy */}
      <div className="h-9 bg-cohere-black text-on-dark flex items-center justify-center px-lg">
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

      {/* Top nav — three-zone: logo / menu / sign-in+CTA */}
      <header className="border-b border-hairline bg-canvas">
        <div className="mx-auto max-w-[1200px] px-lg flex items-center h-16 gap-8">
          {/* Logo left */}
          <Link
            to="/"
            className="font-display text-card-heading tracking-tight text-ink shrink-0"
          >
            WhatsApp Bot
          </Link>

          {/* Menu center */}
          <nav className="flex-1 flex items-center justify-center gap-8">
            {nav.map((item) => {
              const active =
                item.to === "/"
                  ? location.pathname === "/"
                  : location.pathname.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`text-caption transition ${
                    active
                      ? "text-ink"
                      : "text-muted hover:text-ink"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* Right zone — user + logout */}
          <div className="flex items-center gap-4 shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-soft-stone text-ink flex items-center justify-center text-caption font-medium uppercase">
                {user?.username?.[0] ?? "?"}
              </div>
              <span
                className="text-caption text-ink max-w-[120px] truncate"
                title={user?.username ?? ""}
              >
                {user?.username ?? "(unknown)"}
              </span>
            </div>
            <button onClick={handleLogout} className="btn-pill-outline">
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* Main content — generous section padding per Cohere whitespace philosophy */}
      <main className="flex-1">
        <div className="mx-auto max-w-[1200px] px-lg py-section">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
