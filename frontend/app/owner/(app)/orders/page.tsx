"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { OrderCard } from "@/components/orders/OrderCard";
import { OrderDrawer } from "@/components/orders/OrderDrawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { BOARD_COLUMNS } from "@/lib/orderStatus";
import type { OwnerOrderCard, ShopOwner } from "@/lib/types";

const POLL_MS = 3000;

type View = "board" | "cancelled";

export default function OrdersBoard() {
  const toast = useToast();
  const [view, setView] = useState<View>("board");
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [orders, setOrders] = useState<OwnerOrderCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false); // a poll failed after data was shown
  const [now, setNow] = useState(() => Date.now());
  const [openId, setOpenId] = useState<number | null>(null);
  const [slug, setSlug] = useState<string | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const load = useCallback(async () => {
    const id = ++seq.current;
    const params = new URLSearchParams();
    if (view === "cancelled") params.set("status", "cancelled");
    if (debouncedQ) params.set("q", debouncedQ);
    try {
      const res = await api<{ items: OwnerOrderCard[] }>(`/owner/orders?${params}`, { role: "owner" });
      if (id !== seq.current) return; // a newer request (filter changed) is in flight
      setOrders(res.items);
      setError(null);
      setStale(false);
      setNow(Date.now());
    } catch (e) {
      if (id !== seq.current) return;
      const msg = e instanceof ApiError ? e.message : "Could not load orders.";
      setStale(true);
      setError((prev) => prev ?? msg);
    }
  }, [view, debouncedQ]);

  // refetch right away when the filter changes, then every 3 seconds
  useEffect(() => {
    setOrders(null);
    setError(null);
    void load();
    const t = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    api<ShopOwner>("/owner/shop", { role: "owner" })
      .then((s) => setSlug(s.slug))
      .catch(() => setSlug(null));
  }, []);

  const shopLink = slug && typeof window !== "undefined" ? `${window.location.origin}/shop/${slug}` : null;
  async function copyLink() {
    if (!shopLink) return;
    try {
      await navigator.clipboard.writeText(shopLink);
      toast.show("Shop link copied.", "success");
    } catch {
      toast.show(shopLink, "info");
    }
  }

  const filtering = debouncedQ.length > 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Orders</p>
          <h1 className="text-4xl">Order board</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="order-search" className="sr-only">
            Search orders
          </label>
          <input
            id="order-search"
            className="input !w-56 !py-2"
            placeholder="Search #1042, phone, item"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div role="tablist" aria-label="Board view" className="flex rounded-full border-[3px] border-ink bg-white p-1">
            {(["board", "cancelled"] as const).map((v) => (
              <button
                key={v}
                type="button"
                role="tab"
                aria-selected={view === v}
                onClick={() => setView(v)}
                className={`rounded-full px-4 py-1.5 text-sm font-semibold ${view === v ? "border-2 border-ink bg-butter shadow-brutal-sm" : ""}`}
              >
                {v === "board" ? "Board" : "Cancelled"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {stale && orders && (
        <p role="status" className="rounded-2xl bg-cream-yellow p-2 text-center text-sm">
          Can&apos;t reach the server. Showing the last update, retrying every few seconds…
        </p>
      )}

      {orders === null && !error ? (
        <div className="card flex h-48 items-center justify-center">
          <Spinner label="Loading orders…" />
        </div>
      ) : orders === null && error ? (
        <ErrorState message={error} onRetry={load} />
      ) : orders && orders.length === 0 ? (
        <EmptyState
          icon="🧾"
          title={filtering ? "No orders match your search" : view === "cancelled" ? "No cancelled orders" : "No orders yet. Share your shop link."}
          hint={
            filtering
              ? "Try a different order number, phone or item."
              : view === "cancelled"
                ? "Cancelled orders will show up here."
                : "New orders appear here within a few seconds of the customer confirming."
          }
          action={
            !filtering && view === "board" && shopLink ? (
              <div className="flex flex-wrap items-center justify-center gap-2">
                <code className="chip break-all font-mono text-xs">{shopLink}</code>
                <button type="button" className="btn-primary !py-2 text-sm" onClick={copyLink}>
                  Copy link
                </button>
              </div>
            ) : undefined
          }
        />
      ) : view === "cancelled" || filtering ? (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Orders">
          {orders!.map((o) => (
            <li key={o.id}>
              <OrderCard order={o} now={now} onOpen={() => setOpenId(o.id)} />
            </li>
          ))}
        </ul>
      ) : (
        <div className="-mx-4 overflow-x-auto px-4 pb-4 sm:-mx-6 sm:px-6" data-testid="board">
          <div className="grid min-w-[1260px] grid-cols-6 gap-3">
            {BOARD_COLUMNS.map((col) => {
              const list = orders!.filter((o) => o.status === col.status);
              return (
                <section key={col.status} aria-label={col.label} className="flex flex-col gap-2">
                  <h2 className={`flex items-center justify-between rounded-full border-[3px] border-ink px-3 py-1.5 font-sans text-sm font-bold ${col.tone}`}>
                    <span>{col.label}</span>
                    <span className="rounded-full bg-white px-2 text-xs" data-testid="count">{list.length}</span>
                  </h2>
                  {list.length === 0 ? (
                    <p className="rounded-2xl border-2 border-dashed border-ink/20 p-3 text-center text-xs text-muted">Nothing here</p>
                  ) : (
                    list.map((o) => <OrderCard key={o.id} order={o} now={now} onOpen={() => setOpenId(o.id)} />)
                  )}
                </section>
              );
            })}
          </div>
        </div>
      )}

      {openId !== null && <OrderDrawer orderId={openId} onClose={() => setOpenId(null)} onChanged={() => void load()} />}
    </div>
  );
}
