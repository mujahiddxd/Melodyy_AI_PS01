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
