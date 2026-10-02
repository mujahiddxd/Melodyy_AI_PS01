import { age, rupees2 } from "@/lib/format";
import type { OwnerOrderCard } from "@/lib/types";

/** One order on the board: number, masked phone, item count, total, age, "requested by", red dot for problems. */
export function OrderCard({ order, now, onOpen }: { order: OwnerOrderCard; now: number; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      data-testid="order-card"
      aria-label={`Order ${order.order_no}${order.has_problem ? ", needs attention" : ""}`}
      className="relative w-full rounded-2xl border-[3px] border-ink bg-white p-3 text-left shadow-clay transition duration-150 hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-sm"
    >
      {order.has_problem && (
        <span
          title="Needs attention"
          aria-hidden
          className="absolute -right-1.5 -top-1.5 h-4 w-4 rounded-full border-2 border-ink bg-danger"
          data-testid="problem-dot"
        />
      )}
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-display text-lg">#{order.order_no}</span>
        <span className="text-xs text-muted">{age(order.updated_at, now)}</span>
      </div>
      <p className="mt-0.5 font-mono text-xs text-muted">{order.customer_phone_masked ?? "phone not verified"}</p>
      <div className="mt-2 flex items-center justify-between gap-2 text-sm">
        <span>
          {order.item_count} item{order.item_count === 1 ? "" : "s"}
        </span>
        <span className="font-display text-base">{order.total !== "0.00" ? rupees2(order.total) : "not billed"}</span>
      </div>
      {order.requested_delivery_text && (
        <p className="mt-1.5 truncate rounded-full bg-cream-yellow px-2 py-0.5 text-xs" title={order.requested_delivery_text}>
          ⏰ by {order.requested_delivery_text}
        </p>
      )}
    </button>
  );
}
