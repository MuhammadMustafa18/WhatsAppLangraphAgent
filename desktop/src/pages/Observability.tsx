import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api/client";

interface LogEntry {
  event: string;
  level: string;
  timestamp: string;
  [key: string]: unknown;
}

const LEVEL_ORDER = ["error", "warning", "info", "debug"];
const LEVEL_COLORS: Record<string, string> = {
  error: "text-red-600 bg-red-50 border-red-200",
  warning: "text-amber-700 bg-amber-50 border-amber-200",
  info: "text-ink/70",
  debug: "text-gray-400",
};
const LEVEL_BADGE: Record<string, string> = {
  error: "bg-red-100 text-red-700",
  warning: "bg-amber-100 text-amber-700",
  info: "bg-gray-100 text-gray-600",
  debug: "bg-gray-50 text-gray-400",
};

export default function Observability() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [levelFilter, setLevelFilter] = useState<string>("all");
  const [paused, setPaused] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (paused) return;
    const controller = new AbortController();

    async function poll() {
      try {
        const res = await apiFetch("/logs?lines=500", { signal: controller.signal });
        if (!res.ok) return;
        const data = await res.json();
        setLogs(data.lines ?? []);
      } catch {
        // ignore
      }
    }

    poll();
    const interval = setInterval(poll, 3000);
    return () => {
      controller.abort();
      clearInterval(interval);
    };
  }, [paused]);

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, autoScroll]);

  const filtered = logs.filter((e) =>
    levelFilter === "all" ? true : e.level === levelFilter,
  );

  const visible = [...filtered].reverse();

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="mono-label text-muted mb-1">MONITORING</p>
          <h1 className="font-display text-section-heading text-ink">
            Observability
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-xs border border-hairline overflow-hidden">
            {["all", ...LEVEL_ORDER].map((lvl) => (
              <button
                key={lvl}
                onClick={() => setLevelFilter(lvl)}
                className={`px-3 py-1.5 text-micro font-medium transition ${
                  levelFilter === lvl
                    ? "bg-ink text-white"
                    : "bg-canvas text-muted hover:text-ink"
                }`}
              >
                {lvl === "all" ? "All" : lvl.charAt(0).toUpperCase() + lvl.slice(1)}
              </button>
            ))}
          </div>
          <button
            onClick={() => setPaused((p) => !p)}
            className={`px-3 py-1.5 text-micro font-medium rounded-xs border border-hairline transition ${
              paused ? "bg-amber-50 text-amber-700 border-amber-200" : "text-muted hover:text-ink"
            }`}
          >
            {paused ? "Paused" : "Pause"}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto rounded-xs border border-hairline bg-white">
        {visible.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-caption text-muted">
            No log entries yet
          </div>
        ) : (
          <div className="font-mono text-micro">
            {visible.map((entry, i) => {
              const ts = (entry.timestamp ?? "").slice(11, 23);
              const level = entry.level ?? "info";
              const event = entry.event ?? "";
              const extras = Object.entries(entry).filter(
                ([k]) => !["event", "level", "timestamp", "logger", "exc_info", "stack"].includes(k),
              );
              return (
                <div
                  key={`${ts}-${i}`}
                  className={`flex items-start gap-2 px-3 py-1.5 border-b border-hairline/50 hover:bg-soft-stone/30 ${
                    LEVEL_COLORS[level] ?? "text-ink/70"
                  }`}
                >
                  <span className="shrink-0 w-14 text-gray-400 tabular-nums">
                    {ts}
                  </span>
                  <span
                    className={`shrink-0 w-14 text-center rounded px-1 text-[10px] font-semibold uppercase ${
                      LEVEL_BADGE[level] ?? "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {level}
                  </span>
                  <span className="shrink-0 font-medium min-w-[120px]">
                    {event}
                  </span>
                  <span className="text-muted truncate">
                    {extras.map(([k, v]) => (
                      <span key={k} className="whitespace-nowrap">
                        <span className="text-gray-400">{k}</span>
                        <span className="text-muted">={String(v)} </span>
                      </span>
                    ))}
                  </span>
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="flex items-center justify-between mt-2 text-micro text-muted">
        <span>{visible.length} entries (last 500)</span>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="accent-ink"
          />
          Auto-scroll
        </label>
      </div>
    </div>
  );
}
