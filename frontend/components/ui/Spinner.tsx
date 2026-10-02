export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-3 text-muted">
      <span className="h-5 w-5 animate-spin rounded-full border-[3px] border-ink border-t-transparent" />
      <span className="text-sm">{label}</span>
    </div>
  );
}
