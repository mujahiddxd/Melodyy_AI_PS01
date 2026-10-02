import { EmptyState } from "@/components/ui/EmptyState";
import { MockBadge } from "@/components/ui/MockBadge";

export default function OrdersPlaceholder() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="eyebrow">Orders</p>
        <h1 className="text-4xl">Order board</h1>
      </div>
      <EmptyState
        icon="🧾"
        title="No orders yet"
        hint="Customer orders will appear here once chat ordering is built (Stage 4)."
        action={<MockBadge>PLACEHOLDER</MockBadge>}
      />
    </div>
  );
}
