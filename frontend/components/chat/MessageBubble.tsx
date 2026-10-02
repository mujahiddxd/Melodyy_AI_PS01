import { clock } from "@/lib/format";
import type { ChatMessage } from "@/lib/types";

export function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.sender === "system" || message.type === "system") {
    return (
      <div className="flex justify-center">
        <span className="chip !py-1 text-xs text-muted">{message.content}</span>
      </div>
    );
  }
  const mine = message.sender === "customer";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] border-[3px] border-ink px-4 py-2.5 sm:max-w-[75%] ${
          mine ? "rounded-3xl rounded-br-md bg-lavender" : "rounded-3xl rounded-bl-md bg-white"
        }`}
      >
        {!mine && <p className="eyebrow mb-0.5">{message.sender === "shopkeeper" ? "Shop" : "Order desk"}</p>}
        <p className="whitespace-pre-wrap break-words" lang={/[ऀ-ॿ]/.test(message.content) ? "hi" : undefined}>
          {message.content}
        </p>
        <p className="mt-1 text-right text-[11px] text-muted">{clock(message.created_at)}</p>
      </div>
    </div>
  );
}

/** The customer's own message while it is being sent (or failed to send). */
export function PendingBubble({
  text,
  failed,
  onResend,
}: {
  text: string;
  failed: boolean;
  onResend: () => void;
}) {
  return (
    <div className="flex justify-end">
      <div
        className={`max-w-[85%] rounded-3xl rounded-br-md border-[3px] px-4 py-2.5 sm:max-w-[75%] ${
          failed ? "border-danger bg-danger-fill" : "border-ink bg-lavender opacity-80"
        }`}
      >
        <p className="whitespace-pre-wrap break-words">{text}</p>
        <div className="mt-1 flex items-center justify-end gap-2 text-[11px]">
          {failed ? (
            <>
              <span className="font-semibold text-danger">Not sent</span>
              <button type="button" onClick={onResend} className="btn-secondary !px-3 !py-0.5 text-xs">
                Resend
              </button>
            </>
          ) : (
            <span className="text-muted">Sending…</span>
          )}
        </div>
      </div>
    </div>
  );
}

export function TypingBubble() {
  return (
    <div className="flex justify-start" role="status" aria-label="The order desk is typing">
      <div className="flex items-center gap-1.5 rounded-3xl rounded-bl-md border-[3px] border-ink bg-white px-4 py-3.5">
        {[0, 1, 2].map((n) => (
          <span
            key={n}
            className="h-2.5 w-2.5 animate-bounce rounded-full bg-ink"
            style={{ animationDelay: `${n * 150}ms` }}
          />
        ))}
        <span className="sr-only">typing…</span>
      </div>
    </div>
  );
}
