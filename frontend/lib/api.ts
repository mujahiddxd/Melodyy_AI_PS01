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
    const err = new ApiError(message, res.status, code);
    if (role) handleSessionExpired(role, err);
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** An owner call came back 401: the token is gone or expired. Clear it and send them to log in. */
export function handleSessionExpired(role: TokenRole, e: unknown): boolean {
  if (!(e instanceof ApiError) || e.status !== 401 || role !== "owner") return false;
  setToken("owner", null);
  if (typeof window !== "undefined") window.location.assign("/owner/login?expired=1");
  return true;
}

/** multipart upload with progress (fetch can't report upload progress). */
export function uploadFile<T>(
  path: string,
  file: File,
  role: TokenRole,
  onProgress?: (percent: number) => void,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}${path}`);
    const token = getToken(role);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable && onProgress) onProgress(Math.round((ev.loaded / ev.total) * 100));
    };
    xhr.onerror = () => reject(new ApiError("Can't reach the server. Check your connection and try again.", 0));
    xhr.ontimeout = () => reject(new ApiError("The upload timed out. Please try again.", 0));
    xhr.timeout = 60000;
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // non-JSON body
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as T);
      } else {
        const { message, code } = readableDetail(body as ErrorBody | null, `Upload failed (${xhr.status})`);
        const err = new ApiError(message, xhr.status, code);
        handleSessionExpired(role, err);
        reject(err);
      }
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
