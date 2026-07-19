// Tiny hand-rolled modal. One file, no library dep.
// Closes on Escape, click outside the panel, or X button.

import { useEffect, ReactNode } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  maxWidth?: string; // tailwind class, e.g. "max-w-md"
}

export default function Modal({
  title,
  onClose,
  children,
  maxWidth = "max-w-md",
}: ModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 bg-cohere-black/40 flex items-center justify-center z-50 px-4"
      onClick={onClose}
    >
      <div
        className={`bg-canvas rounded-lg border border-card-border p-8 w-full ${maxWidth}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-6 gap-6">
          <h2 className="text-card-heading text-ink">{title}</h2>
          <button
            onClick={onClose}
            className="text-muted hover:text-ink text-2xl leading-none -mt-1"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
