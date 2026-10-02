"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";

export const MAX_CHARS = 1000;

export function Composer({ disabled, onSend }: { disabled: boolean; onSend: (text: string) => void }) {
  const [text, setText] = useState("");
  const canSend = text.trim().length > 0 && !disabled;

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!canSend) return;
    onSend(text);
    setText("");
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="border-t-[3px] border-ink bg-white p-3" aria-label="Send a message">
      <div className="flex items-end gap-2">
        <button
          type="button"
          disabled
          aria-label="Voice order (coming soon)"
          title="Voice orders: coming soon"
          className="btn-secondary !h-11 !w-11 shrink-0 !p-0"
        >
          🎤
        </button>
        <button
          type="button"
          disabled
          aria-label="Photo of a handwritten list (coming soon)"
          title="Photo of your list: coming soon"
          className="btn-secondary !h-11 !w-11 shrink-0 !p-0"
        >
          📷
        </button>
        <label htmlFor="chat-input" className="sr-only">
          Your order
        </label>
        <textarea
          id="chat-input"
          rows={1}
          value={text}
          maxLength={MAX_CHARS}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          placeholder="Type your order, e.g. 2 kilo atta aur ek packet namak"
          className="input max-h-32 min-h-[44px] flex-1 resize-none !py-2.5"
        />
        <button type="submit" disabled={!canSend} className="btn-primary !h-11 shrink-0 !px-5">
          Send →
        </button>
      </div>
      <p className="mt-1.5 flex justify-between text-[11px] text-muted">
        <span>Mic and camera: coming soon</span>
        {text.length > MAX_CHARS * 0.8 && (
          <span>
            {text.length}/{MAX_CHARS}
          </span>
        )}
      </p>
    </form>
  );
}
