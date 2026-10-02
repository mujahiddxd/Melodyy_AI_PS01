// Fetch wrapper. Adds the Bearer token and turns {detail} errors into readable messages.
// Contract: see /API_CONTRACT.md.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type TokenRole = "owner" | "customer";
const TOKEN_KEYS: Record<TokenRole, string> = { owner: "owner_token", customer: "customer_token" };
const memory: Partial<Record<TokenRole, string | null>> = {};

export function getToken(role: TokenRole): string | null {
  if (memory[role] !== undefined) return memory[role] ?? null;
  if (typeof window === "undefined") return null;
  try {
    memory[role] = window.localStorage.getItem(TOKEN_KEYS[role]);
  } catch {
    memory[role] = null;
  }
  return memory[role] ?? null;
}

export function setToken(role: TokenRole, token: string | null): void {
  memory[role] = token;
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEYS[role], token);
    else window.localStorage.removeItem(TOKEN_KEYS[role]);
  } catch {
    // storage unavailable: the in-memory copy still works for this tab
  }
}

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type ErrorBody = { detail?: unknown };

function readableDetail(body: ErrorBody | null, fallback: string): { message: string; code?: string } {
  const d = body?.detail;
  if (typeof d === "string") return { message: d };
  if (Array.isArray(d)) {
    // FastAPI validation errors: [{loc, msg, type}]
    const msgs = d.map((e) => (e && typeof e === "object" && "msg" in e ? String((e as { msg: unknown }).msg) : ""));
    return { message: msgs.filter(Boolean).join("; ") || fallback };
  }
  if (d && typeof d === "object") {
    const o = d as { code?: string; message?: string };
    return { message: o.message ?? fallback, code: o.code };
  }
  return { message: fallback };
}

export interface RequestOptions extends Omit<RequestInit, "body" | "headers"> {
  role?: TokenRole;
  json?: unknown;
  body?: BodyInit;
  headers?: Record<string, string>;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { role, json, headers = {}, ...rest } = opts;
  const h: Record<string, string> = { ...headers };
  if (json !== undefined) h["Content-Type"] = "application/json";
  const token = role ? getToken(role) : null;
  if (token) h["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...rest,
      headers: h,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }

  if (!res.ok) {
    let body: ErrorBody | null = null;
    try {
      body = await res.json();
    } catch {
      // non-JSON error body
    }
    const { message, code } = readableDetail(body, `Request failed (${res.status})`);
    throw new ApiError(message, res.status, code);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
