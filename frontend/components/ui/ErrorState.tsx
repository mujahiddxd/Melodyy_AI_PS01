export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-card border-[3px] border-danger bg-danger-fill p-6 text-center">
      <h3 className="text-xl text-danger">Something went wrong</h3>
      <p className="mt-1 text-ink">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary mt-4">
          Try again
        </button>
      )}
    </div>
  );
}
