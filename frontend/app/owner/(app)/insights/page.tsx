import { EmptyState } from "@/components/ui/EmptyState";
import { MockBadge } from "@/components/ui/MockBadge";

export default function InsightsPlaceholder() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="eyebrow">Insights</p>
        <h1 className="text-4xl">Sales and stock insights</h1>
      </div>
      <EmptyState
        icon="📈"
        title="Insights are coming"
        hint="Sales, top items and low-stock alerts arrive in Stage 7."
        action={<MockBadge>PLACEHOLDER</MockBadge>}
      />
    </div>
  );
}
