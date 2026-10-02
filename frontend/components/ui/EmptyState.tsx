import type { ReactNode } from "react";

export function EmptyState({
  title,
  hint,
  action,
  icon = "🛒",
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  icon?: string;
}) {
  return (
    <div className="card flex flex-col items-center gap-3 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-sky text-2xl">{icon}</div>
      <h3 className="text-xl">{title}</h3>
      {hint && <p className="max-w-sm text-muted">{hint}</p>}
      {action}
    </div>
  );
}
