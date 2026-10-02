"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AgentStrip } from "@/components/chat/AgentStrip";
import { ClarificationChips } from "@/components/chat/ClarificationChips";
import { Composer } from "@/components/chat/Composer";
import { DraftOrderCard } from "@/components/chat/DraftOrderCard";
import { MessageBubble, PendingBubble, TypingBubble } from "@/components/chat/MessageBubble";
import { Suggestions } from "@/components/chat/Suggestions";
import { CustomerBar } from "@/components/customer/CustomerBar";
import { DeliveryAddress, type ChosenAddress } from "@/components/customer/DeliveryAddress";
import { OtpModal } from "@/components/customer/OtpModal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { MockBadge } from "@/components/ui/MockBadge";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { api, ApiError } from "@/lib/api";
import { useCustomer } from "@/lib/customer";
import type { PublicShopResponse, ShopPublic } from "@/lib/types";
import { useChat } from "@/lib/useChat";

export default function ChatPage() {
  const { slug } = useParams<{ slug: string }>();
  const { customer } = useCustomer();
  const chat = useChat(slug);

  const [shop, setShop] = useState<ShopPublic | null>(null);
  const [shopError, setShopError] = useState<{ message: string; notFound: boolean } | null>(null);
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [otpOpen, setOtpOpen] = useState(false);
  const [address, setAddress] = useState<ChosenAddress | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const loadShop = useCallback(async () => {
    setShopError(null);
    try {
      setShop((await api<PublicShopResponse>(`/shops/${encodeURIComponent(slug)}`)).shop);
    } catch (e) {
      setShopError({
        message: e instanceof ApiError ? e.message : "Could not load this shop.",
        notFound: e instanceof ApiError && e.status === 404,
      });
    }
  }, [slug]);

  useEffect(() => {
    loadShop();
  }, [loadShop]);

  const { messages, pending, sending, order, runs, retryText } = chat;
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, pending, sending, retryText]);

  const lastBotId = [...messages].reverse().find((m) => m.sender === "bot")?.id;
  const lastMessageId = messages[messages.length - 1]?.id;
  const ready = !!customer && !!address?.eligible;

  // ---- whole-page states
  if (shopError?.notFound) {
    return (
      <main className="mx-auto max-w-[1200px] px-4 py-8 sm:px-6">
        <EmptyState icon="🔍" title="Shop not found" hint="Check the link and try again." />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-[1200px] px-4 py-5 sm:px-6">
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <Link href={`/shop/${slug}`} className="font-display text-lg">
          ← Shop
        </Link>
        <h1 className="min-w-0 flex-1 truncate text-2xl">{shop ? shop.name : "Order chat"}</h1>
        {chat.llmMock && <MockBadge>DEMO / MOCK AI</MockBadge>}
        <button type="button" className="btn-secondary !py-2 text-sm" onClick={() => setVerifyOpen(true)}>
          {customer ? "✓ Verified · Address" : "Verify & address"}
        </button>
      </header>

      {shopError && !shopError.notFound && (
        <div className="mb-4">
          <ErrorState message={shopError.message} onRetry={loadShop} />
        </div>
      )}

      {chat.phase === "loading" ? (
        <div className="card flex h-64 items-center justify-center">
          <Spinner label="Opening your chat…" />
        </div>
      ) : chat.phase === "error" ? (
        <ErrorState message={chat.initError ?? "Could not open the chat."} onRetry={chat.start} />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
          <section
            className="card flex h-[calc(100dvh-9.5rem)] min-h-[520px] flex-col overflow-hidden !p-0"
            aria-label="Chat"
          >
            <div className="flex-1 space-y-3 overflow-y-auto p-4" role="log" aria-live="polite" aria-label="Messages">
              {messages.length === 0 && !pending ? (
                <Suggestions disabled={chat.sending} onPick={chat.send} />
              ) : (
                messages.map((m) => (
                  <div key={m.id}>
                    <MessageBubble message={m} />
                    {m.id === lastBotId && order && m.meta?.clarification_ids && !chat.sending && (
                      <ClarificationChips
                        order={order}
                        clarificationIds={m.meta.clarification_ids}
                        disabled={chat.sending}
                        onPick={(c, o) =>
                          chat.answer(c, { optionProductId: o.product_id, label: `${o.label} · ${o.pack}` })
                        }
                        onSkip={(c) => chat.answer(c, { text: "skip", label: "Skip this item" })}
                      />
                    )}
                    {m.id === lastMessageId && m.meta?.error === "LLM_FAILED" && retryText && !chat.sending && (
                      <div className="mt-2 flex justify-start pl-1">
                        <button type="button" className="btn-primary !py-2 text-sm" onClick={chat.retry}>
                          ↻ Retry
                        </button>
                      </div>
                    )}
                  </div>
                ))
              )}
              {pending && <PendingBubble text={pending.text} failed={pending.failed} onResend={chat.retry} />}
              {chat.sending && <TypingBubble />}

              {/* phones: the draft order sits inside the chat; desktop shows it in the side panel */}
              {(order || chat.sending) && (
                <div className="lg:hidden">
                  <DraftOrderCard order={order} loading={chat.sending} />
                </div>
              )}
              <div ref={bottom} />
            </div>

            <AgentStrip active={chat.sending} runs={runs} />
            <Composer disabled={chat.sending} onSend={chat.send} />
          </section>

          <aside className="hidden lg:block">
            <div className="sticky top-5 space-y-4">
              <DraftOrderCard order={order} loading={chat.sending} />
              {messages.length > 0 && (
                <button type="button" className="btn-secondary w-full text-sm" onClick={chat.reset} disabled={chat.sending}>
                  Start a new chat
                </button>
              )}
            </div>
          </aside>
        </div>
      )}

      {verifyOpen && (
        <Modal title="Verify & delivery address" onClose={() => setVerifyOpen(false)}>
          <div className="flex flex-col gap-5">
            <p className="text-muted">
              You only need this before confirming an order. Chatting stays open to everyone.
            </p>
            <CustomerBar onVerify={() => setOtpOpen(true)} />
            {shopError ? (
              <ErrorState message={shopError.message} onRetry={loadShop} />
            ) : !shop ? (
              <Spinner label="Loading shop…" />
            ) : (
              <DeliveryAddress shop={shop} onRequestVerify={() => setOtpOpen(true)} onChange={setAddress} />
            )}
            <div className="flex flex-wrap items-center gap-3 border-t-[3px] border-ink/10 pt-4">
              <span className={`badge border-2 border-ink ${customer ? "bg-mint" : "bg-white"}`}>
                {customer ? "✓" : "○"} Phone verified
              </span>
              <span className={`badge border-2 border-ink ${address?.eligible ? "bg-mint" : "bg-white"}`}>
                {address?.eligible ? "✓" : "○"} Address in delivery area
              </span>
              <button
                type="button"
                className="btn-primary ml-auto"
                disabled={!ready}
                title="Bill and confirmation arrive in the next step"
                onClick={() => setVerifyOpen(false)}
              >
                {ready ? "Done ✓" : "Done"}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {otpOpen && (
        <OtpModal
          onClose={() => setOtpOpen(false)}
          onVerified={() => {
            chat.claim();
          }}
        />
      )}
    </main>
  );
}
