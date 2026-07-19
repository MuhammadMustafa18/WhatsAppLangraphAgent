import type { SidecarId } from "../lib/health";

export type SidecarStatus = "pending" | "ok" | "error";

export default function LoadingScreen({
  services,
  error,
  onRetry,
}: {
  services: Record<SidecarId, { label: string; status: SidecarStatus }>;
  error?: string | null;
  onRetry?: () => void;
}) {
  const allOk = Object.values(services).every((s) => s.status === "ok");
  const hasError = error != null || Object.values(services).some((s) => s.status === "error");

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-canvas">
      <div className="w-[320px] text-center">
        <div
          className={`mx-auto mb-8 h-7 w-7 rounded-full border-2 border-hairline border-t-primary ${
            allOk ? "" : "animate-spin"
          }`}
        />

        <p className="mono-label text-muted mb-8">
          {hasError ? "Couldn't start the app" : "Starting up"}
        </p>

        <ul className="space-y-3 text-left">
          {(Object.entries(services) as [SidecarId, { label: string; status: SidecarStatus }][]).map(
            ([id, svc]) => (
              <li key={id} className="flex items-center gap-3 text-caption">
                <StatusDot status={svc.status} />
                <span className={svc.status === "ok" ? "text-ink" : "text-body-muted"}>
                  {svc.label}
                </span>
              </li>
            ),
          )}
        </ul>

        {hasError && (
          <div className="mt-10">
            {error && (
              <p className="mb-4 text-caption text-body-muted">{error}</p>
            )}
            {onRetry && (
              <button onClick={onRetry} className="btn-primary">
                Retry
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusDot({ status }: { status: SidecarStatus }) {
  if (status === "ok") {
    return (
      <svg
        className="h-4 w-4 text-deep-green"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden
      >
        <path
          fillRule="evenodd"
          d="M16.704 5.296a1 1 0 010 1.408l-7.5 7.5a1 1 0 01-1.408 0l-3.5-3.5a1 1 0 011.408-1.408L8.5 12.092l6.796-6.796a1 1 0 011.408 0z"
          clipRule="evenodd"
        />
      </svg>
    );
  }
  if (status === "error") {
    return <span className="h-2 w-2 rounded-full bg-error" aria-hidden />;
  }
  return (
    <span
      className="h-2 w-2 animate-pulse rounded-full bg-muted"
      aria-hidden
    />
  );
}
