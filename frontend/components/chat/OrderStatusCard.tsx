"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { clock, PAYMENT_LABEL, rupees2 } from "@/lib/format";
import { LIVE_POLL_MS } from "@/lib/useChat";
import type { CustomerOrderResponse, OrderStatus, StatusEvent } from "@/lib/types";

const STEPS: { status: OrderStatus; label: string; icon: string }[] = [
  { status: "confirmed", label: "Confirmed", icon: "✓" },
  { status: "packing", label: "Packing", icon: "📦" },
  { status: "out_for_delivery", label: "Out for delivery", icon: "🛵" },
  { status: "delivered", label: "Delivered", icon: "🏠" },
];
const TERMINAL: OrderStatus[] = ["delivered", "cancelled"];

function when(timeline: StatusEvent[], status: OrderStatus): string | null {
  const e = [...timeline].reverse().find((x) => x.to_status === status);
  return e ? clock(e.created_at) : null;
}

/**
 * "Order #1042 confirmed ✓" with a Confirmed → Packing → Out for delivery → Delivered timeline.
 * Polls GET /orders/{id} every 5 seconds until the order is delivered or cancelled.
 */
export function OrderStatusCard({
  orderId,
  orderNo,
  headers,
}: {
  orderId: number;
  orderNo: number;
  headers: () => Record<string, string>;
}) {
  const [data, setData] = useState<CustomerOrderResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const done = useRef(false);

  const load = useCallback(async () => {
    try {
      const res = await api<CustomerOrderResponse>(`/orders/${orderId}`, { role: "customer", headers: headers() });
      setData(res);
      setError(null);
      setStale(false);
      done.current = TERMINAL.includes(res.order.status);
    } catch (e) {
      // first load failed: show the error; later failures keep the last data and say we are reconnecting
      if (e instanceof ApiError && [401, 403, 404].includes(e.status)) done.current = true;
      setStale(true);
      setError((prev) => prev ?? (e instanceof ApiError ? e.message : "Could not load the order."));
    }
  }, [orderId, headers]);

  useEffect(() => {
    void load();
    const t = setInterval(() => {
      if (!done.current) void load();
    }, LIVE_POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  if (!data) {
    return (
      <section className="card !p-4" aria-label={`Order ${orderNo}`}>
        {error ? (
          <div role="alert" className="text-sm">
            <p className="font-semibold text-danger">Order #{orderNo} is confirmed, but its status could not be loaded.</p>
            <p className="text-muted">{error}</p>
            <button type="button" className="btn-secondary mt-2 !py-1.5 text-sm" onClick={() => void load()}>
              Try again
            </button>
          </div>
        ) : (
          <div className="space-y-2" role="status" aria-label="Loading order status">
            <div className="h-6 w-2/3 animate-pulse rounded-xl bg-cream" />
            <div className="h-12 animate-pulse rounded-2xl bg-cream" />
          </div>
        )}
      </section>
    );
  }

  const { order, timeline } = data;
  const cancelled = order.status === "cancelled";
  const current = STEPS.findIndex((s) => s.status === order.status);
  const cancelNote = [...timeline].reverse().find((e) => e.to_status === "cancelled")?.note;

  return (
    <section
      className={`card !p-4 ${cancelled ? "!bg-danger-fill" : "!bg-mint"}`}
      aria-label={`Order ${orderNo} status`}
      data-testid="order-status-card"
    >
      <h3 className="text-xl">
        {cancelled ? `Order #${orderNo} cancelled` : `Order #${orderNo} confirmed ✓`}
      </h3>
      {cancelled ? (
        <p className="mt-1 text-sm">
          {cancelNote ? `Reason: ${cancelNote}. ` : ""}Nothing was charged and the stock was released.
        </p>
      ) : (
        <>
          <p className="mt-0.5 text-sm">
            {rupees2(order.total)} · {PAYMENT_LABEL[order.payment_method ?? "cod"]} (pay when it arrives)
          </p>
          <ol className="mt-4 grid grid-cols-4 gap-1" aria-label="Order progress">
            {STEPS.map((s, i) => {
              const state = i < current || order.status === "delivered" ? "done" : i === current ? "now" : "todo";
              return (
                <li key={s.status} className="flex flex-col items-center gap-1 text-center">
                  <span
                    aria-current={state === "now" ? "step" : undefined}
                    className={`flex h-11 w-11 items-center justify-center rounded-full border-[3px] border-ink text-lg ${
                      state === "done" ? "bg-ink text-white" : state === "now" ? "bg-butter shadow-brutal-sm" : "bg-white text-muted"
                    }`}
                  >
                    {state === "done" ? "✓" : s.icon}
                  </span>
                  <span className={`text-xs leading-tight ${state === "todo" ? "text-muted" : "font-semibold"}`}>{s.label}</span>
                  <span className="text-[11px] text-muted">{when(timeline, s.status) ?? " "}</span>
                </li>
              );
            })}
          </ol>
        </>
      )}
      {order.delivery_address_text && (
        <p className="mt-3 text-xs text-muted">Delivering to: {order.delivery_address_text}</p>
      )}
      {stale && !TERMINAL.includes(order.status) && (
        <p className="mt-2 text-xs text-muted" role="status">
          Reconnecting… showing the last known status.
        </p>
      )}
    </section>
  );
}
