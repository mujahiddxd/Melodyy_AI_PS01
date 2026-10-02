"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Health } from "@/lib/types";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";

type State = { kind: "loading" } | { kind: "online"; health: Health } | { kind: "error"; message: string };

export function BackendStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const check = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const health = await api<Health>("/health");
      setState({ kind: "online", health });
    } catch (e) {
      setState({ kind: "error", message: e instanceof ApiError ? e.message : "Backend is offline." });
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  if (state.kind === "loading") return <Spinner label="Checking backend…" />;
  if (state.kind === "error") return <ErrorState message={`Backend: offline. ${state.message}`} onRetry={check} />;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="badge border-2 border-ink bg-mint">Backend: online</span>
      <span className={`badge border-2 border-ink ${state.health.db === "ok" ? "bg-mint" : "bg-danger-fill"}`}>
        Database: {state.health.db}
      </span>
    </div>
  );
}
