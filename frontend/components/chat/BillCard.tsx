"use client";

import { useState } from "react";
import { km, PAYMENT_LABEL, rupees, rupees2, unitLabel } from "@/lib/format";
import type { Bill, BillLine } from "@/lib/types";
import type { ChosenAddress } from "@/components/customer/DeliveryAddress";

/** A coded problem from POST /orders/{id}/confirm, shown inline under the bill. */
export interface ConfirmProblem {
  code: string;
  message: string;
  data: Record<string, unknown>;
}

function lineText(l: BillLine): string {
  // "2 kg × ₹45/kg = ₹90.00" for loose items, "×4 × ₹25 = ₹100.00" reads badly, so packs say "4 × ₹25"
  const loose = l.unit !== "pack";
  const price = loose ? `${rupees(l.unit_price)}/${unitLabel(l.unit)}` : rupees(l.unit_price);
  const qty = loose ? l.qty_label : l.qty_label.replace("×", "");
  return `${qty} × ${price} = ${rupees2(l.line_total)}`;
}

export function ConfirmProblemAlert({ p, shopRadius }: { p: ConfirmProblem; shopRadius?: number }) {
  const d = p.data;
  if (p.code === "STOCK_CHANGED") {
    const items = (d.items as { product_name: string; available_qty: string }[]) ?? [];
    return (
      <div role="alert" className="rounded-2xl border-[3px] border-danger bg-danger-fill p-3 text-sm">
        <p className="font-semibold text-danger">Stock changed, nothing was ordered yet</p>
        <ul className="mt-1 list-disc pl-5">
          {items.map((i) => (
            <li key={i.product_name}>
              {i.product_name}: {parseFloat(i.available_qty) > 0 ? `only ${parseFloat(i.available_qty)} left` : "out of stock"}
            </li>
          ))}
        </ul>
        <p className="mt-1 text-muted">Please answer the question below, then confirm again.</p>
      </div>
    );
  }
  if (p.code === "PRICE_CHANGED") {
    const changes = (d.changes as { product_name: string; old_price: string | null; new_price: string }[]) ?? [];
    return (
      <div role="alert" className="rounded-2xl border-[3px] border-ink bg-butter p-3 text-sm">
        <p className="font-semibold">Price changed, please check the new bill</p>
        <ul className="mt-1 list-disc pl-5">
          {changes.map((c) => (
            <li key={c.product_name}>
              {c.product_name}: {c.old_price ? rupees2(c.old_price) : "—"} → {rupees2(c.new_price)}
            </li>
          ))}
        </ul>
        <p className="mt-1">
          Total {rupees2(String(d.old_total))} → <b>{rupees2(String(d.new_total))}</b>. Tap “Confirm order” again to
          approve it.
        </p>
      </div>
    );
  }
  if (p.code === "OUT_OF_RADIUS") {
    return (
      <div role="alert" className="rounded-2xl border-[3px] border-danger bg-danger-fill p-3 text-sm">
        <p className="font-semibold text-danger">
          Sorry, this shop delivers within {km(Number(d.radius_km ?? shopRadius ?? 0))}. Your address is{" "}
          {Number(d.distance_km).toFixed(2)} km away.
        </p>
        <p className="mt-1 text-muted">Choose an address inside the delivery area to order.</p>
      </div>
    );
  }
  return (
    <div role="alert" className="rounded-2xl border-[3px] border-danger bg-danger-fill p-3 text-sm font-semibold text-danger">
      {p.message}
    </div>
  );
}

export function BillCard({
  bill,
  active,
  address,
  addressLoading,
  verified,
  confirming,
  problem,
  onConfirm,
  onEdit,
  onChooseAddress,
  onCancel,
}: {
  bill: Bill;
  /** The latest bill of an order that still waits for confirmation. Older bills are read-only. */
  active: boolean;
  address: ChosenAddress | null;
  addressLoading: boolean;
  verified: boolean;
  confirming: boolean;
  problem: ConfirmProblem | null;
  onConfirm: () => void;
  onEdit: () => void;
  onChooseAddress: () => void;
  onCancel: () => void;
}) {
  const hasDiscount = parseFloat(bill.discount) > 0;
  const [armed, setArmed] = useState(false); // cancelling asks for a second tap
  return (
    <section
      className={`card !p-4 ${active ? "" : "opacity-70"}`}
      aria-label={`Bill for order ${bill.order_no}`}
      data-testid="bill-card"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="eyebrow">Bill</p>
          <h3 className="text-xl">Order #{bill.order_no}</h3>
        </div>
        {!active ? (
          <span className="badge border-2 border-ink/30 bg-white text-muted">Earlier bill</span>
        ) : bill.requires_reapproval ? (
          <span className="badge border-2 border-ink bg-butter">Price updated</span>
        ) : null}
      </div>

      <ul className="mt-3 divide-y-2 divide-ink/10">
        {bill.lines.map((l) => (
          <li key={l.item_id} className="flex items-baseline justify-between gap-3 py-2">
            <span className="min-w-0">
              <span className="block font-semibold leading-tight">{l.name}</span>
              <span className="block text-sm text-muted">{lineText(l)}</span>
            </span>
            <span className="shrink-0 font-display text-lg">{rupees2(l.line_total)}</span>
          </li>
        ))}
      </ul>

      <dl className="mt-2 space-y-1 border-t-[3px] border-ink pt-3 text-sm">
        <div className="flex justify-between">
          <dt className="text-muted">Subtotal</dt>
          <dd>{rupees2(bill.subtotal)}</dd>
        </div>
        {hasDiscount && (
          <div className="flex justify-between">
            <dt className="text-muted">Discount</dt>
            <dd>−{rupees2(bill.discount)}</dd>
          </div>
        )}
        <div className="flex justify-between">
          <dt className="text-muted">Delivery fee</dt>
          <dd>{parseFloat(bill.delivery_fee) > 0 ? rupees2(bill.delivery_fee) : "Free"}</dd>
        </div>
        <div className="flex items-center justify-between rounded-2xl bg-mint px-3 py-2 text-base">
          <dt className="font-semibold">Total</dt>
          <dd className="font-display text-2xl" data-testid="bill-total">
            {rupees2(bill.total)}
          </dd>
        </div>
      </dl>

      {active && (
        <>
          <div className="mt-3 rounded-2xl bg-cream p-3 text-sm">
            <p className="eyebrow">Deliver to</p>
            {addressLoading ? (
              <p className="mt-1 text-muted">Looking for your saved address…</p>
            ) : !address ? (
              <p className="mt-1">
                <span className="text-muted">No address yet. </span>
                <button type="button" className="font-semibold underline" onClick={onChooseAddress}>
                  Choose delivery address
                </button>
              </p>
            ) : (
              <p className="mt-1">
                <span className={`font-semibold ${address.eligible ? "" : "text-danger"}`}>
                  {address.eligible ? "✓" : "✗"} {address.address_text || "Pinned location"}
                </span>{" "}
                <span className="text-muted">
                  ({address.eligible ? "inside delivery area" : "outside delivery area"}, {km(address.distance_km)})
                </span>{" "}
                <button type="button" className="font-semibold underline" onClick={onChooseAddress}>
                  Change
                </button>
              </p>
            )}
          </div>

          <div className="mt-3" role="radiogroup" aria-label="Payment method">
            <p className="eyebrow mb-1.5">Payment</p>
            <div className="flex flex-wrap gap-2">
              <span role="radio" aria-checked className="chip chip-active">
                ✓ {PAYMENT_LABEL.cod}
              </span>
              <span role="radio" aria-checked={false} aria-disabled className="chip opacity-50">
                UPI · coming soon
              </span>
            </div>
          </div>

          {problem && (
            <div className="mt-3">
              <ConfirmProblemAlert p={problem} />
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn-primary flex-1"
              onClick={onConfirm}
              disabled={confirming}
              aria-busy={confirming}
            >
              {confirming ? "Confirming…" : verified ? "Confirm order" : "Verify phone & confirm"}
            </button>
            <button type="button" className="btn-secondary" onClick={onEdit} disabled={confirming}>
              Edit
            </button>
          </div>
          <button
            type="button"
            className={`mt-2 text-xs font-semibold underline ${armed ? "text-danger" : "text-muted"}`}
            onClick={() => (armed ? onCancel() : setArmed(true))}
            onBlur={() => setArmed(false)}
            disabled={confirming}
          >
            {armed ? "Tap again to cancel the whole order" : "Cancel this order"}
          </button>
        </>
      )}
    </section>
  );
}
