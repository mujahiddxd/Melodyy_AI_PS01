import type { ProductPublic } from "./types";

export function trimQty(v: string | number): string {
  // "10.000" -> "10", "0.500" -> "0.5"
  const n = typeof v === "number" ? v : parseFloat(v);
  if (Number.isNaN(n)) return String(v);
  return String(Number(n.toFixed(3)));
}

export function rupees(v: string | number): string {
  const n = typeof v === "number" ? v : parseFloat(v);
  return `₹${Number.isInteger(n) ? n : n.toFixed(2)}`;
}

const UNIT_LABEL: Record<string, string> = { g: "g", kg: "kg", ml: "ml", l: "L", pc: "pc", dozen: "dozen", packet: "packet" };

export function unitLabel(unit: string): string {
  return UNIT_LABEL[unit] ?? unit;
}

/** "1 kg pack" for packed items, "per kg" for loose ones. */
export function packLabel(p: Pick<ProductPublic, "sell_mode" | "pack_size" | "pack_unit">): string {
  return p.sell_mode === "loose"
    ? `per ${unitLabel(p.pack_unit)}`
    : `${trimQty(p.pack_size)} ${unitLabel(p.pack_unit)}`;
}

export const PHONE_RE = /^[6-9]\d{9}$/;
export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;
export const VPA_RE = /^[\w.\-]{2,}@\w{2,}$/;

export function cleanPhone(raw: string): string {
  let d = raw.replace(/[\s-]/g, "");
  if (d.startsWith("+91")) d = d.slice(3);
  else if (d.length === 12 && d.startsWith("91")) d = d.slice(2);
  return d;
}

/** "+91 98••••3210" */
export function maskPhone(phone: string): string {
  return `+91 ${phone.slice(0, 2)}••••${phone.slice(-4)}`;
}

export function km(v: number): string {
  return `${Number(v.toFixed(v < 10 ? 1 : 0))} km`;
}

/** "09:41 am" in the viewer's timezone. */
export function clock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** "just now", "5 min", "2 h", "3 d": how long ago, for board cards. */
export function age(iso: string, now: number = Date.now()): string {
  const secs = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} min`;
  const hours = Math.floor(mins / 60);
  return hours < 24 ? `${hours} h` : `${Math.floor(hours / 24)} d`;
}

/** Order number as shown everywhere: "#1042". */
export function orderNo(n: number): string {
  return `#${n}`;
}

/** "5 Oct, 09:41 am" in the viewer's timezone. */
export function dateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.toLocaleDateString([], { day: "numeric", month: "short" })}, ${clock(iso)}`;
}

/** Always two decimals: "₹113.00" (bills and totals). */
export function rupees2(v: string | number): string {
  const n = typeof v === "number" ? v : parseFloat(v);
  return `₹${(Number.isNaN(n) ? 0 : n).toFixed(2)}`;
}

export const PAYMENT_LABEL: Record<string, string> = {
  cod: "Cash on Delivery",
  upi: "UPI",
  razorpay: "Online payment",
};
