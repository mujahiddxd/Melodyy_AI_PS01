"use client";

import { useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";

export const MAX_CHARS = 1000;

export function Composer({
  disabled,
  onSend,
  onSendImage,
}: {
  disabled: boolean;
  onSend: (text: string) => void;
  onSendImage?: (file: File) => void;
}) {
  const [text, setText] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
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

  function onFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !onSendImage) return;
    onSendImage(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
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
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={onFileChange}
          aria-hidden
        />
        <button
          type="button"
          disabled={disabled || !onSendImage}
          onClick={() => fileInputRef.current?.click()}
          aria-label="Upload photo of handwritten shopping list"
          title="Upload photo of your shopping list"
          className="btn-secondary !h-11 !w-11 shrink-0 !p-0 hover:bg-butter"
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
          placeholder="Type your order, or upload a photo of your list 📷"
          className="input max-h-32 min-h-[44px] flex-1 resize-none !py-2.5"
        />
        <button type="submit" disabled={!canSend} className="btn-primary !h-11 shrink-0 !px-5">
          Send →
        </button>
      </div>
      <p className="mt-1.5 flex justify-between text-[11px] text-muted">
        <span>📷 Photo list OCR active · Mic: coming soon</span>
        {text.length > MAX_CHARS * 0.8 && (
          <span>
            {text.length}/{MAX_CHARS}
          </span>
        )}
      </p>
    </form>
  );
}
