"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ui/ErrorState";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="card max-w-md text-center">
        <ErrorState
          message={error.message || "An unexpected error occurred while loading this page."}
          onRetry={reset}
        />
      </div>
    </main>
  );
}
