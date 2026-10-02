"use client";

import { useEffect, type ReactNode } from "react";

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 sm:p-8"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div role="dialog" aria-modal="true" aria-label={title} className="card my-auto w-full max-w-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-2xl">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="btn-secondary !px-4 !py-1.5">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
