import type { OrderStatus } from "./types";

/** Board columns, left to right (Cancelled is a filter, not a column). */
export const BOARD_COLUMNS: { status: OrderStatus; label: string; tone: string }[] = [
  { status: "needs_clarification", label: "Needs clarification", tone: "bg-butter" },
  { status: "awaiting_confirmation", label: "Awaiting confirmation", tone: "bg-cream-yellow" },
  { status: "confirmed", label: "Confirmed", tone: "bg-mint" },
  { status: "packing", label: "Packing", tone: "bg-sky" },
  { status: "out_for_delivery", label: "Out for delivery", tone: "bg-lavender" },
  { status: "delivered", label: "Delivered", tone: "bg-white" },
];

export const STATUS_LABEL: Record<OrderStatus, string> = {
  draft: "Draft",
  needs_clarification: "Needs clarification",
  awaiting_confirmation: "Awaiting confirmation",
  confirmed: "Confirmed",
  packing: "Packing",
  out_for_delivery: "Out for delivery",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

export const STATUS_TONE: Record<OrderStatus, string> = {
  draft: "bg-white",
  needs_clarification: "bg-butter",
  awaiting_confirmation: "bg-cream-yellow",
  confirmed: "bg-mint",
  packing: "bg-sky",
  out_for_delivery: "bg-lavender",
  delivered: "bg-white",
  cancelled: "bg-danger-fill text-danger",
};

/** Button text for the shopkeeper's next step. */
export const NEXT_ACTION: Partial<Record<OrderStatus, string>> = {
  packing: "Start packing",
  out_for_delivery: "Send out for delivery",
  delivered: "Mark delivered",
};
