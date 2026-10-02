"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { confidenceTone } from "@/components/chat/DraftOrderCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { clock, dateTime, km, PAYMENT_LABEL, rupees2, trimQty, unitLabel } from "@/lib/format";
import { NEXT_ACTION, STATUS_LABEL, STATUS_TONE } from "@/lib/orderStatus";
import type { OrderStatus, OwnerOrderDetail } from "@/lib/types";

const MiniMap = dynamic(() => import("@/components/map/MiniMap"), {
  ssr: false,
  loading: () => <div className="flex h-48 items-center justify-center rounded-2xl border-[3px] border-ink bg-white"><Spinner label="Loading map…" /></div>,
});

const POLL_MS = 3000;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="eyebrow mb-2">{title}</h3>
      {children}
    </section>
  );
}

function pretty(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

export function OrderDrawer({ orderId, onClose, onChanged }: { orderId: number; onClose: () => void; onChanged: () => void }) {
  const toast = useToast();
  const [data, setData] = useState<OwnerOrderDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [openRun, setOpenRun] = useState<number | null>(null);
  const acting_ = useRef(false);

  const load = useCallback(async () => {
    try {
      setData(await api<OwnerOrderDetail>(`/owner/orders/${orderId}`, { role: "owner" }));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load this order.");
    }
  }, [orderId]);

  useEffect(() => {
    setData(null);
    setError(null);
    setCancelling(false);
    setReason("");
    setActionError(null);
    void load();
    const t = setInterval(() => {
      if (!acting_.current) void load();
    }, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function move(to: OrderStatus, note?: string) {
    if (acting_.current) return; // a double click must not send two moves
    acting_.current = true;
    setActing(true);
    setActionError(null);
    try {
      await api(`/owner/orders/${orderId}/status`, { method: "POST", role: "owner", json: { to, note: note ?? null } });
      toast.show(to === "cancelled" ? "Order cancelled. Stock was put back." : `Order moved to ${STATUS_LABEL[to]}.`, "success");
      setCancelling(false);
      setReason("");
      onChanged();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Could not update the order.");
      onChanged();
    } finally {
      acting_.current = false;
      setActing(false);
      void load();
    }
  }

  const order = data?.order;
  const nextSteps = (data?.allowed_next ?? []).filter((s) => s !== "cancelled");
  const canCancel = !!data?.allowed_next.includes("cancelled");
  const waiting = !!order && ["draft", "needs_clarification", "awaiting_confirmation"].includes(order.status);
  const items = order?.items.filter((i) => i.status !== "removed") ?? [];

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink/40 print:hidden" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={order ? `Order ${order.order_no}` : "Order details"}
        className="h-full w-full max-w-xl overflow-y-auto border-l-[3px] border-ink bg-cream p-5"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="eyebrow">Order</p>
            <h2 className="text-3xl">{order ? `#${order.order_no}` : "…"}</h2>
          </div>
          <div className="flex items-center gap-2">
            {order && <span className={`badge border-2 border-ink ${STATUS_TONE[order.status]}`}>{STATUS_LABEL[order.status]}</span>}
            <button type="button" onClick={onClose} aria-label="Close" className="btn-secondary !px-4 !py-1.5">
              ✕
            </button>
          </div>
        </div>

        {!data && !error && (
          <div className="mt-8">
            <Spinner label="Loading order…" />
          </div>
        )}
        {error && !data && (
          <div className="mt-6">
            <ErrorState message={error} onRetry={load} />
          </div>
        )}
        {error && data && (
          <p role="status" className="mt-3 rounded-2xl bg-cream-yellow p-2 text-center text-xs">
            Reconnecting… showing the last known details.
          </p>
        )}

        {data && order && (
          <>
            {data.problems.length > 0 && (
              <ul className="mt-4 space-y-1 rounded-2xl border-[3px] border-danger bg-danger-fill p-3 text-sm font-semibold text-danger" role="alert">
                {data.problems.map((p) => (
                  <li key={p}>● {p}</li>
                ))}
              </ul>
            )}

            {/* actions first: this is what the shopkeeper came for */}
            <Section title="Next step">
              {actionError && (
                <p role="alert" className="mb-2 rounded-2xl border-[3px] border-danger bg-danger-fill p-2 text-sm font-semibold text-danger">
                  {actionError}
                </p>
              )}
              {waiting && (
                <p className="mb-2 rounded-2xl bg-cream-yellow p-3 text-sm">
                  {order.status === "awaiting_confirmation"
                    ? "Waiting for the customer to confirm the bill."
                    : "Waiting for the customer to answer a question in the chat."}
                </p>
              )}
              {["delivered", "cancelled"].includes(order.status) && (
                <p className="mb-2 rounded-2xl bg-white p-3 text-sm shadow-clay">This order is {STATUS_LABEL[order.status].toLowerCase()}. No further steps.</p>
              )}
              <div className="flex flex-wrap gap-2">
                {nextSteps.map((to) => (
                  <button key={to} type="button" className="btn-primary" disabled={acting} onClick={() => move(to)}>
                    {acting ? "Updating…" : NEXT_ACTION[to] ?? `Mark ${STATUS_LABEL[to]}`}
                  </button>
                ))}
                {canCancel && !cancelling && (
                  <button type="button" className="btn-secondary !border-danger !text-danger" disabled={acting} onClick={() => setCancelling(true)}>
                    Cancel order
                  </button>
                )}
              </div>
              {cancelling && (
                <div className="mt-3 rounded-2xl border-[3px] border-danger bg-danger-fill p-3">
                  <label htmlFor="cancel-reason" className="text-sm font-semibold">
                    Reason for cancelling (the customer will see it)
                  </label>
                  <textarea
                    id="cancel-reason"
                    className="input mt-1.5 min-h-[72px]"
                    maxLength={300}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="e.g. Item is out of stock, sorry"
                  />
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      className="btn-primary !bg-danger !shadow-none"
                      disabled={acting || reason.trim().length < 3}
                      onClick={() => move("cancelled", reason.trim())}
                    >
                      {acting ? "Cancelling…" : "Confirm cancel"}
                    </button>
                    <button type="button" className="btn-secondary" disabled={acting} onClick={() => setCancelling(false)}>
                      Keep order
                    </button>
                  </div>
                  {["confirmed", "packing", "out_for_delivery"].includes(order.status) && (
                    <p className="mt-2 text-xs text-muted">Stock that was reserved for this order is put back automatically.</p>
                  )}
                </div>
              )}
            </Section>

            <Section title="Customer">
              <div className="rounded-2xl bg-white p-3 shadow-clay text-sm">
                <p>
                  <span className="text-muted">Phone: </span>
                  <span className="font-mono">{data.customer.phone_masked ?? "not verified yet"}</span>
                </p>
                {order.requested_delivery_text && (
                  <p>
                    <span className="text-muted">Requested by: </span>
                    {order.requested_delivery_text}
                  </p>
                )}
                <p>
                  <span className="text-muted">Placed: </span>
                  {dateTime(order.created_at)}
                </p>
              </div>
            </Section>

            <Section title="What the customer wrote">
              {data.messages.length === 0 ? (
                <p className="rounded-2xl bg-white p-3 text-sm text-muted shadow-clay">No messages are linked to this order.</p>
              ) : (
                <ul className="space-y-2">
                  {data.messages.map((m) => (
                    <li key={m.id} className="rounded-3xl rounded-bl-md border-[3px] border-ink bg-lavender px-4 py-2 text-sm">
                      <p className="whitespace-pre-wrap break-words">{m.content}</p>
                      <p className="mt-0.5 text-right text-[11px] text-muted">{clock(m.created_at)}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title="Parsed items">
              {items.length === 0 ? (
                <EmptyState icon="🧺" title="No items" hint="This order has no items yet." />
              ) : (
                <ul className="space-y-2">
                  {items.map((i) => {
                    const tone = confidenceTone(i.confidence);
                    return (
                      <li key={i.id} className="rounded-2xl bg-white p-3 shadow-clay" data-testid="owner-item">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="font-semibold leading-tight">{i.product_name ?? i.name_guess}</p>
                            <p className="text-xs text-muted">
                              “{i.raw_text}” → {i.product_qty !== null ? trimQty(i.product_qty) : "?"}{" "}
                              {i.product ? (i.product.sell_mode === "loose" ? unitLabel(i.product.pack_unit) : "pack") : ""}
                            </p>
                          </div>
                          <p className="shrink-0 font-display text-lg">{i.line_total ? rupees2(i.line_total) : "—"}</p>
                        </div>
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          <span className={`badge border-2 ${tone.cls}`} title="Match confidence">
                            {Math.round(i.confidence * 100)}% {tone.label}
                          </span>
                          {i.status !== "matched" && <span className="badge border-2 border-danger bg-danger-fill text-danger">{i.status.replace("_", " ")}</span>}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Section>

            <Section title="Bill">
              {!data.bill ? (
                <p className="rounded-2xl bg-white p-3 text-sm text-muted shadow-clay">No bill yet: the customer is still choosing.</p>
              ) : (
                <dl className="space-y-1 rounded-2xl bg-white p-3 text-sm shadow-clay">
                  <div className="flex justify-between"><dt className="text-muted">Subtotal</dt><dd>{rupees2(data.bill.subtotal)}</dd></div>
                  <div className="flex justify-between"><dt className="text-muted">Delivery fee</dt><dd>{rupees2(data.bill.delivery_fee)}</dd></div>
                  <div className="flex justify-between rounded-xl bg-mint px-2 py-1.5 text-base font-semibold"><dt>Total</dt><dd className="font-display text-xl">{rupees2(data.bill.total)}</dd></div>
                  <div className="flex justify-between pt-1"><dt className="text-muted">Payment</dt><dd>{order.payment_method ? PAYMENT_LABEL[order.payment_method] : "Not chosen yet"}{order.payment_status === "cod" ? " (pay on delivery)" : ""}</dd></div>
                </dl>
              )}
            </Section>

            <Section title="Delivery address">
              {!order.delivery_address_text ? (
                <p className="rounded-2xl bg-white p-3 text-sm text-muted shadow-clay">The address is saved when the customer confirms.</p>
              ) : (
                <div className="space-y-2">
                  <p className="rounded-2xl bg-white p-3 text-sm shadow-clay">
                    {order.delivery_address_text}
                    {order.distance_km !== null && <span className="text-muted"> · {km(order.distance_km)} from the shop</span>}
                  </p>
                  {order.delivery_lat !== null && order.delivery_lng !== null && (
                    <MiniMap
                      delivery={{ lat: order.delivery_lat, lng: order.delivery_lng }}
                      shop={data.shop.lat !== null && data.shop.lng !== null ? { lat: data.shop.lat, lng: data.shop.lng } : null}
                    />
                  )}
                </div>
              )}
            </Section>

            <Section title="Delivery note">
              <a
                className={`btn-secondary ${!order.delivery_address_text ? "pointer-events-none opacity-50" : ""}`}
                href={`/owner/orders/${order.id}/note`}
                target="_blank"
                rel="noopener noreferrer"
                aria-disabled={!order.delivery_address_text}
              >
                🖨️ Open printable delivery note
              </a>
              {!order.delivery_address_text && <p className="mt-1 text-xs text-muted">Available once the customer has confirmed.</p>}
            </Section>

            <Section title="Status history">
              {data.timeline.length === 0 ? (
                <p className="text-sm text-muted">No changes yet.</p>
              ) : (
                <ol className="space-y-1.5">
                  {data.timeline.map((e, n) => (
                    <li key={n} className="flex flex-wrap items-baseline gap-x-2 rounded-2xl bg-white px-3 py-2 text-sm shadow-clay">
                      <span className="font-mono text-xs text-muted">{dateTime(e.created_at)}</span>
                      <span>
                        {e.from_status ? `${STATUS_LABEL[e.from_status]} → ` : ""}
                        <b>{STATUS_LABEL[e.to_status]}</b>
                      </span>
                      <span className="text-xs text-muted">by {e.actor}</span>
                      {e.note && <span className="w-full text-xs">“{e.note}”</span>}
                    </li>
                  ))}
                </ol>
              )}
            </Section>

            <Section title="Agent runs">
              {data.agent_runs.length === 0 ? (
                <p className="text-sm text-muted">No agent runs are linked to this order.</p>
              ) : (
                <ul className="space-y-1.5">
                  {data.agent_runs.map((r) => (
                    <li key={r.id} className="rounded-2xl bg-white p-2 shadow-clay">
                      <button
                        type="button"
                        className="flex w-full items-center justify-between text-left text-sm font-semibold"
                        aria-expanded={openRun === r.id}
                        onClick={() => setOpenRun(openRun === r.id ? null : r.id)}
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
            </Section>
          </>
        )}
      </aside>
    </div>
  );
}
