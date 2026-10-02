"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { api, ApiError } from "@/lib/api";
import { dateTime, PAYMENT_LABEL, rupees2 } from "@/lib/format";
import type { DeliveryNote } from "@/lib/types";

/** Printable delivery note: order #, customer phone, address, requested time, items with quantities, total, payment. */
export default function DeliveryNotePage() {
  const { id } = useParams<{ id: string }>();
  const [note, setNote] = useState<DeliveryNote | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setNote(await api<DeliveryNote>(`/owner/orders/${id}/delivery-note`, { role: "owner" }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the delivery note.");
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!note) {
    return (
      <div className="card flex h-48 items-center justify-center">
        <Spinner label="Loading delivery note…" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="no-print mb-4 flex flex-wrap items-center gap-2 print:hidden">
        <Link href="/owner/orders" className="btn-secondary !py-2 text-sm">
          ← Back to board
        </Link>
        <button type="button" className="btn-primary !py-2 text-sm" onClick={() => window.print()}>
          🖨️ Print
        </button>
      </div>

      <article className="card print:!rounded-none print:!border-2 print:!shadow-none" aria-label={`Delivery note ${note.order_no}`}>
        <header className="flex items-start justify-between gap-4 border-b-[3px] border-ink pb-3">
          <div>
            <p className="eyebrow">Delivery note</p>
            <h1 className="text-4xl">#{note.order_no}</h1>
            <p className="text-sm text-muted">{note.shop_name}</p>
          </div>
          <p className="text-right text-sm text-muted">Placed {dateTime(note.created_at)}</p>
        </header>

        <section className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <h2 className="eyebrow">Deliver to</h2>
            <p className="mt-1 whitespace-pre-wrap font-semibold">{note.delivery_address_text ?? "Address not saved yet"}</p>
            <p className="mt-1 font-mono">{note.customer_phone ?? "Phone not available"}</p>
          </div>
          <div>
            <h2 className="eyebrow">Requested time</h2>
            <p className="mt-1 font-semibold">
              {note.requested_delivery_text ?? (note.requested_delivery_at ? dateTime(note.requested_delivery_at) : "As soon as possible")}
            </p>
          </div>
        </section>

        <table className="mt-5 w-full text-left">
          <thead>
            <tr className="border-b-[3px] border-ink text-sm">
              <th className="py-2">Item</th>
              <th className="py-2 text-right">Qty</th>
              <th className="py-2 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {note.items.map((i) => (
              <tr key={`${i.name}-${i.qty_label}`} className="border-b-2 border-ink/10">
                <td className="py-2 font-semibold">☐ {i.name}</td>
                <td className="py-2 text-right">{i.qty_label}</td>
                <td className="py-2 text-right">{rupees2(i.line_total)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={2} className="pt-3 text-right text-sm text-muted">Delivery fee</td>
              <td className="pt-3 text-right">{rupees2(note.delivery_fee)}</td>
            </tr>
            <tr>
              <td colSpan={2} className="pt-1 text-right font-semibold">Total</td>
              <td className="pt-1 text-right font-display text-2xl">{rupees2(note.total)}</td>
            </tr>
          </tfoot>
        </table>

        <p className="mt-4 rounded-2xl bg-mint p-3 font-semibold print:border-2 print:border-ink">
          Payment: {note.payment_method ? PAYMENT_LABEL[note.payment_method] : "Not chosen"}
          {note.payment_status === "cod" ? ` · collect ${rupees2(note.total)} on delivery` : ""}
        </p>
      </article>
    </div>
  );
}
