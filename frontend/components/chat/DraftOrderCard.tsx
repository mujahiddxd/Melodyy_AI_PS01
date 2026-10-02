import { rupees, trimQty, unitLabel } from "@/lib/format";
import type { Order, OrderItem, OrderItemStatus, OrderStatus } from "@/lib/types";

/** Confidence badge: green >= 0.85, amber 0.6-0.85, red < 0.6 (plan, Stage 3). */
export function confidenceTone(c: number): { cls: string; label: string } {
  if (c >= 0.85) return { cls: "bg-mint border-ink", label: "high" };
  if (c >= 0.6) return { cls: "bg-butter border-ink", label: "medium" };
  return { cls: "bg-danger-fill border-danger text-danger", label: "low" };
}

const STATUS: Record<OrderItemStatus, { label: string; cls: string }> = {
  matched: { label: "Matched", cls: "bg-mint border-ink" },
  ambiguous: { label: "Ambiguous", cls: "bg-butter border-ink" },
  out_of_stock: { label: "Out of stock", cls: "bg-danger-fill border-danger text-danger" },
  unmatched: { label: "Unmatched", cls: "bg-danger-fill border-danger text-danger" },
  vague_qty: { label: "Quantity?", cls: "bg-butter border-ink" },
  removed: { label: "Removed", cls: "bg-white border-ink/30 text-muted" },
  substituted: { label: "Substituted", cls: "bg-sky border-ink" },
  pending_amendment: { label: "Pending", cls: "bg-sky border-ink" },
};

const ORDER_STATUS: Record<OrderStatus, { label: string; cls: string }> = {
  draft: { label: "Draft", cls: "bg-white" },
  needs_clarification: { label: "Needs your answer", cls: "bg-butter" },
  awaiting_confirmation: { label: "Ready to confirm", cls: "bg-mint" },
  confirmed: { label: "Confirmed", cls: "bg-mint" },
  packing: { label: "Packing", cls: "bg-sky" },
  out_for_delivery: { label: "Out for delivery", cls: "bg-sky" },
  delivered: { label: "Delivered", cls: "bg-mint" },
  cancelled: { label: "Cancelled", cls: "bg-danger-fill text-danger" },
};

function quantityText(i: OrderItem): string {
  if (i.quantity_value !== null) return `${trimQty(i.quantity_value)} ${i.unit ? unitLabel(i.unit) : ""}`.trim();
  if (i.product_qty !== null && i.product && i.product.sell_mode === "pack") return `${trimQty(i.product_qty)} pack`;
  return "—";
}

function packText(i: OrderItem): string | null {
  const p = i.product;
  if (!p || i.product_qty === null) return null;
  if (p.sell_mode === "pack") return `${trimQty(i.product_qty)} × ${trimQty(p.pack_size)} ${unitLabel(p.pack_unit)}`;
  return `${trimQty(i.product_qty)} ${unitLabel(p.pack_unit)} loose`;
}

function ItemRow({ item }: { item: OrderItem }) {
  const st = STATUS[item.status];
  const tone = confidenceTone(item.confidence);
  const removed = item.status === "removed";
  const pack = packText(item);
  return (
    <li className={`rounded-2xl bg-white p-3 shadow-clay ${removed ? "opacity-60" : ""}`} data-testid="draft-item">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={`font-semibold leading-tight ${removed ? "line-through" : ""}`}>
            {item.product_name ?? item.name_guess}
          </p>
          <p className="mt-0.5 text-xs text-muted">
            you said “{item.name_guess}”
            {item.product ? ` · ${rupees(item.product.price)}${item.product.sell_mode === "loose" ? `/${unitLabel(item.product.pack_unit)}` : ""}` : ""}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="font-display text-lg leading-tight">{quantityText(item)}</p>
          {pack && <p className="text-xs text-muted">{pack}</p>}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className={`badge border-2 ${st.cls}`}>{st.label}</span>
        <span
          className={`badge border-2 ${tone.cls}`}
          title={`Match confidence ${tone.label}`}
          aria-label={`Confidence ${Math.round(item.confidence * 100)} percent, ${tone.label}`}
        >
          {Math.round(item.confidence * 100)}%
        </span>
      </div>
    </li>
  );
}

export function DraftOrderCard({ order, loading }: { order: Order | null; loading?: boolean }) {
  const items = order?.items ?? [];
  const status = order ? ORDER_STATUS[order.status] : null;
  return (
    <section className="card !p-4" aria-label="Draft order">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="eyebrow">{!order || ["draft", "needs_clarification", "awaiting_confirmation"].includes(order.status) ? "Draft order" : "Your order"}</p>
          <h2 className="text-xl">{order ? `#${order.order_no}` : "Nothing yet"}</h2>
        </div>
        {status && <span className={`badge border-2 border-ink ${status.cls}`}>{status.label}</span>}
      </div>

      {loading && items.length === 0 ? (
        <div className="mt-4 space-y-2" role="status" aria-label="Updating order">
          {[0, 1, 2].map((n) => (
            <div key={n} className="h-16 animate-pulse rounded-2xl bg-cream" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="mt-4 rounded-2xl bg-cream-yellow p-4 text-sm text-muted">
          Your items will show up here as you chat. Try “2 kilo atta aur ek packet namak”.
        </p>
      ) : (
        <ul className="mt-4 space-y-2">
          {items.map((i) => (
            <ItemRow key={i.id} item={i} />
          ))}
        </ul>
      )}

      {order && items.length > 0 && (
        <p className="mt-4 text-xs text-muted">
          {order.status === "awaiting_confirmation"
            ? "The bill is in the chat. Stock is only reserved when you confirm."
            : ["draft", "needs_clarification"].includes(order.status)
              ? "Prices shown are from the shop's catalog. The bill is made once every question is answered. Stock is only reserved when you confirm."
              : "Prices were fixed on the bill you confirmed."}
        </p>
      )}
    </section>
  );
}
