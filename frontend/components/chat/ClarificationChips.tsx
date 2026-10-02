"use client";

import { rupees } from "@/lib/format";
import type { Clarification, ClarificationOption, Order } from "@/lib/types";

const KIND_LABEL: Record<string, string> = {
  ambiguous_product: "Which one?",
  pack_size: "Which pack?",
  out_of_stock: "Not available. Pick another?",
  unmatched: "Not found in this shop",
  vague_qty: "How much?",
};

function Chip({ option, disabled, onPick }: { option: ClarificationOption; disabled: boolean; onPick: () => void }) {
  const out = option.stock_status === "out_of_stock";
  return (
    <button
      type="button"
      disabled={disabled || out}
      onClick={onPick}
      className="chip text-left transition duration-150 hover:-translate-y-0.5 hover:bg-mint hover:ring-[3px] hover:ring-ink disabled:pointer-events-none disabled:opacity-50"
    >
      <span className="block font-semibold leading-tight">{option.label}</span>
      <span className="block text-xs text-muted">
        {option.pack} · {rupees(option.price)}
        {option.stock_status === "low_stock" ? " · low stock" : ""}
        {out ? " · out of stock" : ""}
      </span>
    </button>
  );
}

/**
 * Tappable answers under the bot's question. Chips come straight from the database options of each open
 * clarification (never from the AI's text). Free-text replies work too.
 */
export function ClarificationChips({
  order,
  clarificationIds,
  disabled,
  onPick,
  onSkip,
}: {
  order: Order;
  clarificationIds: number[];
  disabled: boolean;
  onPick: (clar: Clarification, option: ClarificationOption) => void;
  onSkip: (clar: Clarification) => void;
}) {
  const open = order.clarifications.filter((c) => clarificationIds.includes(c.id) && c.resolved_at === null);
  if (open.length === 0) return null;
  const itemName = (c: Clarification) => order.items.find((i) => i.id === c.order_item_id)?.name_guess ?? "item";
  return (
    <div className="mt-2 space-y-3 pl-1" data-testid="clarification-chips">
      {open.map((c) => (
        <div key={c.id} className="rounded-3xl bg-cream-yellow p-3">
          <p className="eyebrow mb-2">
            {itemName(c)} · {KIND_LABEL[c.kind] ?? "Your answer"}
          </p>
          <div className="flex flex-wrap gap-2">
            {c.options.map((o) => (
              <Chip key={o.product_id} option={o} disabled={disabled} onPick={() => onPick(c, o)} />
            ))}
            <button
              type="button"
              disabled={disabled}
              onClick={() => onSkip(c)}
              className="chip text-sm text-muted transition hover:-translate-y-0.5 disabled:opacity-50"
            >
              ✕ Skip this item
            </button>
          </div>
          {c.options.length === 0 && (
            <p className="mt-2 text-xs text-muted">
              {c.kind === "vague_qty" ? "Type the amount, e.g. “2 kilo” or “aadha kilo”." : "Type another name, or skip it."}
            </p>
          )}
        </div>
      ))}
      <p className="text-xs text-muted">Or just reply in your own words.</p>
    </div>
  );
}
