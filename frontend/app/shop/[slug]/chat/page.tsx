"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AgentStrip } from "@/components/chat/AgentStrip";
import { BillCard, ConfirmProblemAlert, type ConfirmProblem } from "@/components/chat/BillCard";
import { ClarificationChips } from "@/components/chat/ClarificationChips";
import { Composer } from "@/components/chat/Composer";
import { DraftOrderCard } from "@/components/chat/DraftOrderCard";
import { MessageBubble, PendingBubble, TypingBubble } from "@/components/chat/MessageBubble";
import { OrderStatusCard } from "@/components/chat/OrderStatusCard";
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
import { useToast } from "@/components/ui/Toast";
import { useCustomer } from "@/lib/customer";
import type { Address, DeliveryCheck, PublicShopResponse, ShopPublic } from "@/lib/types";
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
  const [addrLookupFor, setAddrLookupFor] = useState<number | null>(null); // customer id whose saved addresses were checked
  const [confirming, setConfirming] = useState(false);
  const [problem, setProblem] = useState<ConfirmProblem | null>(null);
  const [resume, setResume] = useState(false); // Confirm was pressed and the customer is being walked through OTP / address
  const askedAddress = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);
  const toast = useToast();

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
  const orderRef = useRef(order);
  orderRef.current = order;

  // A verified customer with a saved address inside the delivery area confirms in one tap: find that address.
  useEffect(() => {
    if (!customer) {
      setAddress(null);
      setAddrLookupFor(null);
      return;
    }
    if (!shop) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await api<{ items: Address[] }>("/customer/addresses", { role: "customer" });
        for (const a of res.items.slice(0, 5)) {
          const chk = await api<DeliveryCheck>(`/shops/${shop.slug}/delivery-check`, {
            method: "POST",
            json: { lat: a.lat, lng: a.lng },
          });
          if (cancelled) return;
          if (chk.eligible) {
            setAddress((prev) =>
              prev?.id
                ? prev
                : {
                    id: a.id,
                    lat: a.lat,
                    lng: a.lng,
                    address_text: a.address_text,
                    label: a.label,
                    eligible: true,
                    distance_km: chk.distance_km,
                  },
            );
            break;
          }
        }
      } catch {
        // no saved address found: the confirm flow asks for one
      } finally {
        if (!cancelled) setAddrLookupFor(customer.id);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [customer, shop]);

  const addrLoading = !!customer && addrLookupFor !== customer.id;

  const doConfirm = useCallback(async () => {
    const o = orderRef.current;
    if (!o || o.status !== "awaiting_confirmation" || !address?.id) return;
    setConfirming(true);
    setProblem(null);
    try {
      await chat.claim(); // the order must belong to the verified customer (idempotent)
      const out = await chat.confirm(o.id, address.id);
      if (out.ok) {
        toast.show(`Order #${out.order.order_no} confirmed.`, "success");
        return;
      }
      setProblem({ code: out.code, message: out.message, data: out.data });
      if (out.code === "OUT_OF_RADIUS") {
        setAddress((a) => (a ? { ...a, eligible: false, distance_km: Number(out.data.distance_km ?? a.distance_km) } : a));
      }
      if (out.code === "NETWORK") toast.show(out.message, "error");
    } finally {
      setConfirming(false);
    }
  }, [address, chat, toast]);

  /** Confirm pressed: verify the phone (OTP modal), then make sure there is an eligible saved address (location
   *  picker), then call confirm. The effect below continues the flow after each modal. */
  function startConfirm() {
    if (confirming) return;
    const o = orderRef.current;
    if (!o || o.status !== "awaiting_confirmation") return;
    setProblem(null);
    askedAddress.current = false;
    if (!customer) {
      setResume(true);
      setOtpOpen(true);
    } else if (addrLoading) {
      setResume(true); // still looking for a saved address: the effect below continues when that is done
    } else if (!address?.id || !address.eligible) {
      askedAddress.current = true;
      setResume(true);
      setVerifyOpen(true);
    } else {
      void doConfirm();
    }
  }

  useEffect(() => {
    if (!resume || otpOpen || verifyOpen) return;
    if (!customer) return setResume(false); // the OTP modal was closed without verifying
    if (addrLoading) return;
    if (address?.id && address.eligible) {
      setResume(false);
      void doConfirm();
    } else if (!askedAddress.current) {
      askedAddress.current = true; // just verified and no usable saved address: ask for one
      setVerifyOpen(true);
    } else {
      setResume(false); // the address picker was closed without a usable address
    }
  }, [resume, otpOpen, verifyOpen, customer, addrLoading, address, doConfirm]);

  function editOrder() {
    document.getElementById("chat-input")?.focus();
    toast.show("Type what to add or change, e.g. “ek kilo cheeni bhi”.", "info");
  }

  async function cancelOrder() {
    const o = orderRef.current;
    if (!o) return;
    if (await chat.cancelOrder(o.id)) toast.show("Order cancelled.", "info");
  }
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, pending, sending, retryText]);

  const lastBotId = [...messages].reverse().find((m) => m.sender === "bot" && m.type !== "bill")?.id;
  const latestBill = [...messages].reverse().find((m) => m.type === "bill" && m.meta?.bill);
  const activeBillId =
    latestBill && order && latestBill.meta?.order_id === order.id && order.status === "awaiting_confirmation"
      ? latestBill.id
      : null;
  const lastMessageId = messages[messages.length - 1]?.id;
  const ready = !!customer && !!address?.eligible && !!address.id;

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
        <Link href="/orders" className="btn-secondary !py-2 text-sm">
          My orders
        </Link>
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
                    {m.type === "bill" && m.meta?.bill ? (
                      <BillCard
                        bill={m.meta.bill}
                        active={m.id === activeBillId}
                        address={address}
                        addressLoading={addrLoading}
                        verified={!!customer}
                        confirming={confirming}
                        problem={problem}
                        onConfirm={startConfirm}
                        onEdit={editOrder}
                        onChooseAddress={() => setVerifyOpen(true)}
                        onCancel={cancelOrder}
                      />
                    ) : m.meta?.kind === "order_confirmed" && typeof m.meta.order_id === "number" ? (
                      <OrderStatusCard
                        orderId={m.meta.order_id}
                        orderNo={m.meta.order_no ?? 1000 + m.meta.order_id}
                        headers={chat.headers}
                      />
                    ) : (
                      <MessageBubble message={m} />
                    )}
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
              {problem && activeBillId === null && (
                <ConfirmProblemAlert p={problem} shopRadius={shop?.delivery_radius_km ?? undefined} />
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
            <Composer disabled={chat.sending} onSend={chat.send} onSendImage={chat.sendImage} />
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
          {resume && (
            <p className="mb-4 rounded-2xl bg-cream-yellow p-3 text-sm font-medium">
              One last step: choose a delivery address inside the shop&apos;s area, then your order is confirmed.
            </p>
          )}
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
              <DeliveryAddress
                shop={shop}
                onRequestVerify={() => setOtpOpen(true)}
                onChange={(a) => a && setAddress(a)}
              />
            )}
            <div className="flex flex-wrap items-center gap-3 border-t-[3px] border-ink/10 pt-4">
              <span className={`badge border-2 border-ink ${customer ? "bg-mint" : "bg-white"}`}>
                {customer ? "✓" : "○"} Phone verified
              </span>
              <span className={`badge border-2 border-ink ${address?.eligible ? "bg-mint" : "bg-white"}`}>
                {address?.eligible ? "✓" : "○"} {address?.id ? "Saved address in delivery area" : "Address in delivery area"}
              </span>
              <button
                type="button"
                className="btn-primary ml-auto"
                disabled={!ready}
                title={address?.eligible && !address.id ? "Save the address first" : undefined}
                onClick={() => setVerifyOpen(false)}
              >
                {resume ? (ready ? "Use this address & confirm ✓" : "Use this address") : ready ? "Done ✓" : "Done"}
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
