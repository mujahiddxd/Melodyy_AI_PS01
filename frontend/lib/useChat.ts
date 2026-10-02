"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "./api";
import type {
  AgentRun,
  ChatMessage,
  ChatResponse,
  Clarification,
  ConfirmResponse,
  ConversationInfo,
  ConversationState,
  CreateConversationResponse,
  Order,
} from "./types";

// One chat per shop, remembered in this browser. The guest token is only used to prove ownership of the conversation.
interface StoredSession {
  id: number;
  guest: string | null;
}

const storageKey = (slug: string) => `chat_session:${slug}`;

function loadSession(slug: string): StoredSession | null {
  try {
    const raw = window.localStorage.getItem(storageKey(slug));
    if (!raw) return null;
    const s = JSON.parse(raw) as StoredSession;
    return typeof s.id === "number" ? s : null;
  } catch {
    return null;
  }
}

function saveSession(slug: string, s: StoredSession | null): void {
  try {
    if (s) window.localStorage.setItem(storageKey(slug), JSON.stringify(s));
    else window.localStorage.removeItem(storageKey(slug));
  } catch {
    // storage unavailable: the chat still works until the page is closed
  }
}

function merge(prev: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const seen = new Set(prev.map((m) => m.id));
  return [...prev, ...incoming.filter((m) => !seen.has(m.id))];
}

/** Result of POST /orders/{id}/confirm, with the coded problems the chat shows inline. */
export type ConfirmOutcome =
  | { ok: true; order: Order }
  | { ok: false; code: string; message: string; data: Record<string, unknown> };

/** Orders confirmed in this chat that are not delivered or cancelled yet: their status messages keep arriving. */
export function liveOrderIds(messages: ChatMessage[]): number[] {
  const last = new Map<number, string>();
  const confirmed = new Set<number>();
  for (const m of messages) {
    const id = m.meta?.order_id;
    if (typeof id !== "number") continue;
    if (m.meta?.kind === "order_confirmed") confirmed.add(id);
    if ((m.meta?.kind === "order_confirmed" || m.meta?.kind === "order_status") && m.meta.status) last.set(id, m.meta.status);
  }
  return Array.from(confirmed).filter((id) => !["delivered", "cancelled"].includes(last.get(id) ?? ""));
}

export const LIVE_POLL_MS = 5000;

export interface Pending {
  text: string;
  failed: boolean;
}

export const NETWORK_MESSAGE = "Can't reach the server. Check your connection and try again.";

export function useChat(slug: string) {
  const toast = useToast();
  const session = useRef<StoredSession | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [initError, setInitError] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ConversationInfo | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [order, setOrder] = useState<Order | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [llmMock, setLlmMock] = useState(false);
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [retryText, setRetryText] = useState<string | null>(null);
  const busy = useRef(false);

  const headers = useCallback((): Record<string, string> => {
    const g = session.current?.guest;
    return g ? { "X-Guest-Session": g } : {};
  }, []);

  const start = useCallback(async () => {
    setPhase("loading");
    setInitError(null);
    try {
      const stored = loadSession(slug);
      if (stored) {
        session.current = stored;
        try {
          const st = await api<ConversationState>(`/conversations/${stored.id}`, { role: "customer", headers: headers() });
          setConversation(st.conversation);
          setMessages(st.messages);
          setOrder(st.order);
          setRuns(st.agent_runs);
          setLlmMock(st.llm_mock);
          setPhase("ready");
          return;
        } catch (e) {
          // not ours any more (new browser, logged out, deleted): start a fresh conversation
          if (!(e instanceof ApiError) || ![401, 403, 404].includes(e.status)) throw e;
          saveSession(slug, null);
          session.current = null;
        }
      }
      const created = await api<CreateConversationResponse>(`/shops/${encodeURIComponent(slug)}/conversations`, {
        method: "POST",
        role: "customer",
      });
      session.current = { id: created.conversation.id, guest: created.guest_session };
      saveSession(slug, session.current);
      setConversation(created.conversation);
      setMessages(created.messages);
      setOrder(created.order);
      setRuns([]);
      setLlmMock(created.llm_mock);
      setPhase("ready");
    } catch (e) {
      setInitError(e instanceof ApiError ? e.message : "Could not open the chat.");
      setPhase("error");
    }
  }, [slug, headers]);

  useEffect(() => {
    start();
  }, [start]);

  const apply = useCallback((res: { messages: ChatMessage[]; order?: Order | null; agent_runs?: AgentRun[] }) => {
    setMessages((prev) => merge(prev, res.messages));
    if (res.order) setOrder(res.order);
    if (res.agent_runs) setRuns(res.agent_runs);
  }, []);

  /** Run one request. `label` is what the customer's bubble shows while it is in flight. */
  const exec = useCallback(
    async (path: string, json: unknown, label: string) => {
      if (busy.current || !session.current) return;
      busy.current = true;
      setSending(true);
      setPending({ text: label, failed: false });
      setRetryText(null);
      try {
        const res = await api<ChatResponse>(path, { method: "POST", role: "customer", headers: headers(), json });
        setPending(null);
        apply(res);
      } catch (e) {
        if (e instanceof ApiError && e.code === "LLM_FAILED") {
          // the server stored the customer's message and a friendly "dobara bhejiye" reply: show both
          setPending(null);
          apply({
            messages: (e.data.messages as ChatMessage[]) ?? [],
            agent_runs: (e.data.agent_runs as AgentRun[]) ?? undefined,
          });
          setRetryText(label);
        } else if (e instanceof ApiError && e.status === 0) {
          setPending({ text: label, failed: true });
          toast.show(NETWORK_MESSAGE, "error");
        } else {
          setPending(null);
          toast.show(e instanceof ApiError ? e.message : "Something went wrong. Please try again.", "error");
        }
      } finally {
        busy.current = false;
        setSending(false);
      }
    },
    [apply, headers, toast],
  );

  const send = useCallback(
    (text: string) => {
      const t = text.trim();
      if (!t || !session.current) return;
      return exec(`/conversations/${session.current.id}/messages`, { type: "text", content: t }, t);
    },
    [exec],
  );

  const answer = useCallback(
    (clar: Clarification, a: { optionProductId?: number; text?: string; label: string }) => {
      if (!session.current) return;
      return exec(
        `/conversations/${session.current.id}/clarifications/${clar.id}/answer`,
        a.optionProductId !== undefined ? { option_product_id: a.optionProductId } : { text: a.text },
        a.label,
      );
    },
    [exec],
  );

  /** Resend the text that failed on the network, or retry after an LLM failure. */
  const retry = useCallback(() => {
    const text = pending?.failed ? pending.text : retryText;
    if (!text) return;
    setPending(null);
    send(text);
  }, [pending, retryText, send]);

  /** After the customer verified their phone: attach this guest conversation to them. Resolves true when the
   *  conversation belongs to the verified customer (the confirm call needs that). */
  const claim = useCallback(async (): Promise<boolean> => {
    const s = session.current;
    if (!s) return false;
    try {
      await api(`/conversations/${s.id}/claim`, { method: "POST", role: "customer", headers: headers() });
      return true;
    } catch {
      return false;
    }
  }, [headers]);

  /** Pull new messages (status updates, bills) and the current order from the server. Never replaces what is shown
   *  while a message is being sent. */
  const refresh = useCallback(async () => {
    const s = session.current;
    if (!s) return;
    try {
      const st = await api<ConversationState>(`/conversations/${s.id}`, { role: "customer", headers: headers() });
      setMessages((prev) => merge(prev, st.messages));
      if (!busy.current) setOrder(st.order);
    } catch {
      // a missed poll is harmless; the next one catches up
    }
  }, [headers]);

  const liveIds = useMemo(() => liveOrderIds(messages), [messages]);
  const hasLive = liveIds.length > 0;
  useEffect(() => {
    if (!hasLive || phase !== "ready") return;
    const t = setInterval(() => void refresh(), LIVE_POLL_MS);
    return () => clearInterval(t);
  }, [hasLive, phase, refresh]);

  /** Confirm the order with COD. Resolves with the outcome; STOCK_CHANGED / PRICE_CHANGED bodies already carry the
   *  new chat messages and order, which are applied here. */
  const confirm = useCallback(
    async (orderId: number, addressId: number): Promise<ConfirmOutcome> => {
      try {
        const res = await api<ConfirmResponse>(`/orders/${orderId}/confirm`, {
          method: "POST",
          role: "customer",
          headers: headers(),
          json: { address_id: addressId, payment_method: "cod" },
        });
        setOrder(res.order);
        await refresh();
        return { ok: true, order: res.order };
      } catch (e) {
        if (!(e instanceof ApiError)) return { ok: false, code: "ERROR", message: "Something went wrong.", data: {} };
        if (e.code === "STOCK_CHANGED" || e.code === "PRICE_CHANGED") {
          apply({ messages: (e.data.messages as ChatMessage[]) ?? [], order: (e.data.order as Order) ?? null });
        }
        return { ok: false, code: e.code ?? (e.status === 0 ? "NETWORK" : "ERROR"), message: e.message, data: e.data };
      }
    },
    [apply, headers, refresh],
  );

  /** Customer cancels the order before confirming it. */
  const cancelOrder = useCallback(
    async (orderId: number): Promise<boolean> => {
      try {
        const res = await api<{ order: Order }>(`/orders/${orderId}/cancel`, {
          method: "POST",
          role: "customer",
          headers: headers(),
          json: {},
        });
        setOrder(res.order);
        await refresh();
        return true;
      } catch (e) {
        toast.show(e instanceof ApiError ? e.message : "Could not cancel the order.", "error");
        return false;
      }
    },
    [headers, refresh, toast],
  );

  const reset = useCallback(() => {
    saveSession(slug, null);
    session.current = null;
    setMessages([]);
    setOrder(null);
    setRuns([]);
    setPending(null);
    setRetryText(null);
    start();
  }, [slug, start]);

  return {
    phase, initError, conversation, messages, order, runs, llmMock, sending, pending, retryText,
    start, send, answer, retry, claim, reset, refresh, confirm, cancelOrder, liveIds, headers,
  };
}
