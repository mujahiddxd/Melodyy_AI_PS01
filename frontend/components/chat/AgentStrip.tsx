"use client";

import { useEffect, useState } from "react";
import type { AgentRun } from "@/lib/types";

const FLOW = ["intake", "parser", "matcher", "inventory", "clarifier", "messaging"];

function Pill({ label, state, ms }: { label: string; state: "done" | "active" | "idle" | "error" | "skipped"; ms?: number | null }) {
  const cls = {
    done: "bg-mint border-ink",
    active: "bg-butter border-ink animate-pulse",
    idle: "bg-white border-ink/20 text-muted",
    error: "bg-danger-fill border-danger text-danger",
    skipped: "bg-white border-ink/30 text-muted",
  }[state];
  const mark = { done: "✓", active: "…", idle: "", error: "✗", skipped: "–" }[state];
  return (
    <span className={`badge shrink-0 gap-1 border-2 ${cls}`}>
      {mark && <span aria-hidden>{mark}</span>}
      {label}
      {ms !== undefined && ms !== null && <span className="font-mono font-normal opacity-70">{ms}ms</span>}
    </span>
  );
}

function pretty(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

/**
 * While a request is in flight: walks through the agent names. Afterwards: the real agent_runs
 * (name, ✓/✗, ms). Click "details" to see each agent's input and output JSON.
 */
export function AgentStrip({ active, runs }: { active: boolean; runs: AgentRun[] }) {
  const [step, setStep] = useState(0);
  const [open, setOpen] = useState(false);
  const [openRun, setOpenRun] = useState<number | null>(null);

  useEffect(() => {
    if (!active) return;
    setStep(0);
    const t = setInterval(() => setStep((s) => Math.min(s + 1, FLOW.length - 1)), 1100);
    return () => clearInterval(t);
  }, [active]);

  if (!active && runs.length === 0) return null;

  return (
    <div className="border-t-[3px] border-ink bg-cream-yellow px-3 py-2" aria-label="Agent status">
      <div className="flex items-center gap-2">
        <span className="eyebrow shrink-0">{active ? "Agents working" : "Agents"}</span>
        <div className="flex min-w-0 flex-1 gap-1.5 overflow-x-auto pb-0.5">
          {active
            ? FLOW.map((name, i) => <Pill key={name} label={name} state={i < step ? "done" : i === step ? "active" : "idle"} />)
            : runs.map((r) => (
                <Pill
                  key={r.id}
                  label={r.agent}
                  state={r.status === "success" ? "done" : r.status === "error" ? "error" : r.status === "skipped" ? "skipped" : "active"}
                  ms={r.duration_ms}
                />
              ))}
        </div>
        {!active && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="chip shrink-0 !px-3 !py-1 text-xs font-semibold"
          >
            {open ? "Hide" : "Details"}
          </button>
        )}
      </div>

      {!active && open && (
        <ul className="mt-2 max-h-64 space-y-1.5 overflow-y-auto">
          {runs.map((r) => (
            <li key={r.id} className="rounded-2xl bg-white p-2 shadow-clay">
              <button
                type="button"
                className="flex w-full items-center justify-between text-left text-sm font-semibold"
                onClick={() => setOpenRun(openRun === r.id ? null : r.id)}
                aria-expanded={openRun === r.id}
              >
                <span>
                  {r.status === "success" ? "✓" : r.status === "error" ? "✗" : r.status === "skipped" ? "–" : "…"} {r.agent}
                </span>
                <span className="font-mono text-xs text-muted">{r.duration_ms ?? "?"} ms</span>
              </button>
              {r.error && <p className="mt-1 break-words font-mono text-xs text-danger">{r.error}</p>}
              {openRun === r.id && (
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {(["input", "output"] as const).map((k) => (
                    <div key={k}>
                      <p className="eyebrow">{k}</p>
                      <pre className="mt-1 max-h-40 overflow-auto rounded-xl bg-cream p-2 font-mono text-[11px] leading-snug">
                        {r[k] === null || r[k] === undefined ? "—" : pretty(r[k])}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
