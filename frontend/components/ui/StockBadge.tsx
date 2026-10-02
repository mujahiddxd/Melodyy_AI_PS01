import { trimQty, unitLabel } from "@/lib/format";
import type { ProductPublic } from "@/lib/types";

export function StockBadge({ p }: { p: Pick<ProductPublic, "stock_status" | "stock_qty" | "sell_mode" | "pack_unit"> }) {
  if (p.stock_status === "out_of_stock") {
    return <span className="badge border-2 border-danger bg-danger-fill text-danger">Out of stock</span>;
  }
  if (p.stock_status === "low_stock") {
    const unit = p.sell_mode === "loose" ? ` ${unitLabel(p.pack_unit)}` : "";
    return <span className="badge border-2 border-ink bg-butter">Only {trimQty(p.stock_qty)}{unit} left</span>;
  }
  return <span className="badge border-2 border-ink bg-mint">In stock</span>;
}
