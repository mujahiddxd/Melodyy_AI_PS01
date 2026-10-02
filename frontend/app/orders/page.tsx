"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { OtpModal } from "@/components/customer/OtpModal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { api, ApiError } from "@/lib/api";
import { useCustomer } from "@/lib/customer";
import { dateTime, maskPhone, rupees2 } from "@/lib/format";
import { STATUS_LABEL, STATUS_TONE } from "@/lib/orderStatus";
import type { CustomerOrderList, CustomerOrderRow } from "@/lib/types";

function OrderRow({ o }: { o: CustomerOrderRow }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="card !p-4" data-testid={o.is_cart ? "cart-row" : "past-row"}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-display text-lg">
            {o.is_cart ? "Cart" : `#${o.order_no}`} · {o.shop_name}
          </p>
          <p className="text-sm text-muted">
            {dateTime(o.confirmed_at ?? o.created_at)} · {o.item_count} item{o.item_count === 1 ? "" : "s"}
            {o.total !== "0.00" && ` · ${rupees2(o.total)}`}
          </p>
        </div>
        <span className={`badge border-2 border-ink ${STATUS_TONE[o.status]}`}>{STATUS_LABEL[o.status]}</span>
        {o.is_cart ? (
          <Link href={`/shop/${o.shop_slug}/chat`} className="btn-primary !py-2 text-sm">
            Continue →
          </Link>
        ) : (
          <button type="button" className="btn-secondary !py-2 text-sm" onClick={() => setOpen((v) => !v)}>
            {open ? "Hide" : "Details"}
          </button>
        )}
      </div>
      {(open || o.is_cart) && (
        <ul className="mt-3 space-y-1 border-t-2 border-dashed border-ink/20 pt-3 text-sm">
          {o.items.map((i, n) => (
            <li key={n} className="flex justify-between gap-3">
              <span>
                {i.name}
                {i.quantity && <span className="text-muted"> · {i.quantity}</span>}
              </span>
              {i.line_total && <span>{rupees2(i.line_total)}</span>}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function OrdersPage() {
  const { customer, loading: authLoading, logout } = useCustomer();
  const [data, setData] = useState<CustomerOrderList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [otpOpen, setOtpOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api<CustomerOrderList>("/customer/orders", { role: "customer" }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load your orders.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (customer) load();
    else setData(null);
  }, [customer, load]);

  return (
    <main className="mx-auto max-w-[800px] px-4 py-6 sm:px-6">
      <header className="mb-5 flex flex-wrap items-center gap-3">
        <Link href="/" className="font-display text-lg">
          ← Home
        </Link>
        <h1 className="min-w-0 flex-1 text-2xl">My orders</h1>
        {customer && (
          <>
            <span className="badge border-2 border-ink bg-mint">✓ {maskPhone(customer.phone)}</span>
            <button type="button" className="btn-secondary !py-2 text-sm" onClick={logout}>
              Log out
            </button>
          </>
        )}
      </header>

      {authLoading ? (
        <Spinner label="Checking login…" />
      ) : !customer ? (
        <EmptyState
          icon="🔐"
          title="Log in to see your orders"
          hint="We use your phone number and a one-time code. Your cart and past orders are kept against it."
          action={
            <button type="button" className="btn-primary" onClick={() => setOtpOpen(true)}>
              → Log in with phone
            </button>
          }
        />
      ) : loading && !data ? (
        <Spinner label="Loading your orders…" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : data && data.cart.length === 0 && data.past.length === 0 ? (
        <EmptyState
          title="No orders yet"
          hint="Pick a shop and tell it what you need."
          action={
            <Link href="/" className="btn-primary">
              Find a shop
            </Link>
          }
        />
      ) : (
        data && (
          <div className="space-y-6">
            {data.cart.length > 0 && (
              <section>
                <h2 className="mb-2 text-xl">Your cart</h2>
                <ul className="space-y-3">
                  {data.cart.map((o) => (
                    <OrderRow key={o.id} o={o} />
                  ))}
                </ul>
              </section>
            )}
            <section>
              <h2 className="mb-2 text-xl">Past orders</h2>
              {data.past.length === 0 ? (
                <p className="text-muted">Nothing confirmed yet.</p>
              ) : (
                <ul className="space-y-3">
                  {data.past.map((o) => (
                    <OrderRow key={o.id} o={o} />
                  ))}
                </ul>
              )}
            </section>
          </div>
        )
      )}

      {otpOpen && <OtpModal onClose={() => setOtpOpen(false)} onVerified={() => setOtpOpen(false)} />}
    </main>
  );
}
