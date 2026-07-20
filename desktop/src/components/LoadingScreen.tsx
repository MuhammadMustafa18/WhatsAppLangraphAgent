import type { SidecarId } from "../lib/health";

export type SidecarStatus = "pending" | "ok" | "error";

export default function LoadingScreen({
  services,
  serviceErrors,
  error,
  onRetry,
}: {
  services: Record<SidecarId, { label: string; status: SidecarStatus }>;
  serviceErrors?: Record<SidecarId, string | null>;
  error?: string | null;
  onRetry?: () => void;
}) {
  const allOk = Object.values(services).every((s) => s.status === "ok");
  const hasError =
    error != null || Object.values(services).some((s) => s.status === "error");

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-canvas">
      <div className="w-[380px] text-center">
        {/* Spinner or checkmark */}
        {allOk ? (
          <svg
            className="mx-auto mb-8 h-7 w-7 text-deep-green"
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
        ) : (
          <div
            className={`mx-auto mb-8 h-7 w-7 rounded-full border-2 border-hairline ${
              hasError
                ? "border-error"
                : "animate-spin border-t-primary"
            }`}
          />
        )}

        <p className="mono-label text-muted mb-8">
          {hasError
            ? "Couldn't start the app"
            : allOk
              ? "Almost ready..."
              : "Starting up"}
        </p>

        <ul className="space-y-4 text-left">
          {(
            Object.entries(services) as [
              SidecarId,
              { label: string; status: SidecarStatus },
            ][]
          ).map(([id, svc]) => {
            const svcErr = serviceErrors?.[id];
            return (
              <li key={id}>
                <div className="flex items-center gap-3 text-caption">
                  <StatusDot status={svc.status} hasError={!!svcErr} />
                  <span
                    className={
                      svc.status === "ok"
                        ? "text-ink"
                        : svc.status === "error"
                          ? "text-error"
                          : "text-body-muted"
                    }
                  >
                    {svc.label}
                  </span>
                  {svc.status === "pending" && (
                    <span className="ml-auto text-xs text-body-muted">
                      connecting...
                    </span>
                  )}
                </div>
                {/* Show specific error message for this service */}
                {svcErr && (
                  <p className="mt-1.5 ml-7 text-xs leading-relaxed text-error/80">
                    {svcErr}
                  </p>
                )}
              </li>
            );
          })}
        </ul>

        {hasError && (
          <div className="mt-10">
            {error && (
              <p className="mb-4 text-caption text-body-muted">{error}</p>
            )}
            {onRetry && (
              <button
                onClick={onRetry}
                className="btn-primary inline-flex items-center gap-2"
              >
                <svg
                  className="h-4 w-4"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden
                >
                  <path
                    fillRule="evenodd"
                    d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1z"
                    clipRule="evenodd"
                  />
                  <path
                    fillRule="evenodd"
                    d="M16 18a1 1 0 01-1-1v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 111.885-.666A5.002 5.002 0 0014.001 13H11a1 1 0 010-2h5a1 1 0 011 1v5a1 1 0 01-1 1z"
                    clipRule="evenodd"
                  />
                </svg>
                Retry
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusDot({
  status,
  hasError,
}: {
  status: SidecarStatus;
  hasError?: boolean;
}) {
  if (status === "ok") {
    return (
      <svg
        className="h-4 w-4 shrink-0 text-deep-green"
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
    return (
      <svg
        className="h-4 w-4 shrink-0 text-error"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden
      >
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
          clipRule="evenodd"
        />
      </svg>
    );
  }
  if (hasError) {
    return (
      <svg
        className="h-4 w-4 shrink-0 text-error/60"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden
      >
        <path
          fillRule="evenodd"
          d="M8.485 3.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 3.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z"
          clipRule="evenodd"
        />
      </svg>
    );
  }
  return (
    <span
      className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-muted"
      aria-hidden
    />
  );
}
